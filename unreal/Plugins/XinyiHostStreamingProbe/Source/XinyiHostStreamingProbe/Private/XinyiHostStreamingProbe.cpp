#include "Modules/ModuleManager.h"

#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/WorldPartitionStreamingSourceComponent.h"
#include "Containers/Ticker.h"
#include "Dom/JsonObject.h"
#include "Engine/Engine.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "HAL/PlatformFileManager.h"
#include "LandscapeComponent.h"
#include "LandscapeHeightfieldCollisionComponent.h"
#include "LandscapeProxy.h"
#include "LandscapeStreamingProxy.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "UObject/UnrealType.h"
#include "WorldPartition/RuntimeHashSet/WorldPartitionRuntimeHashSet.h"
#include "WorldPartition/WorldPartition.h"
#include "WorldPartition/WorldPartitionRuntimeCell.h"
#include "WorldPartition/WorldPartitionRuntimeHash.h"
#include "WorldPartition/WorldPartitionSubsystem.h"

namespace XinyiHostProbe
{
constexpr TCHAR WorldPath[] = TEXT("/Game/XinyiV2/L_XinyiV2_Contract_WP");

struct FPoint
{
    FString Id;
    FString Kind;
    FString ExpectedTile;
    FVector Location;
};

struct FTile
{
    FString Id;
    FVector ExpectedLocation;
};

TSharedPtr<FJsonObject> ReadJson(const FString& Path)
{
    FString Body;
    TSharedPtr<FJsonObject> Object;
    if (!FFileHelper::LoadFileToString(Body, *Path) ||
        !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Body), Object))
    {
        return nullptr;
    }
    return Object;
}

TArray<TSharedPtr<FJsonValue>> VectorJson(const FVector& V)
{
    return {MakeShared<FJsonValueNumber>(V.X), MakeShared<FJsonValueNumber>(V.Y), MakeShared<FJsonValueNumber>(V.Z)};
}

TArray<TSharedPtr<FJsonValue>> StringsJson(const TSet<FString>& Values)
{
    TArray<FString> Sorted = Values.Array();
    Sorted.Sort();
    TArray<TSharedPtr<FJsonValue>> Result;
    for (const FString& Value : Sorted) Result.Add(MakeShared<FJsonValueString>(Value));
    return Result;
}

UWorldPartitionRuntimeHash* GetHash(UWorldPartition* Partition)
{
    if (!Partition) return nullptr;
    const FObjectProperty* Property = FindFProperty<FObjectProperty>(Partition->GetClass(), TEXT("RuntimeHash"));
    return Property ? Cast<UWorldPartitionRuntimeHash>(Property->GetObjectPropertyValue_InContainer(Partition)) : nullptr;
}

TArray<TSharedPtr<FJsonValue>> LoadingRanges(UWorldPartitionRuntimeHash* Hash, int32& Maximum)
{
    Maximum = 0;
    TArray<TSharedPtr<FJsonValue>> Result;
    const UWorldPartitionRuntimeHashSet* Set = Cast<UWorldPartitionRuntimeHashSet>(Hash);
    if (!Set) return Result;
    const FArrayProperty* Array = FindFProperty<FArrayProperty>(Set->GetClass(), TEXT("RuntimeStreamingData"));
    if (!Array) return Result;
    FScriptArrayHelper Helper(Array, Array->ContainerPtrToValuePtr<void>(Set));
    for (int32 Index = 0; Index < Helper.Num(); ++Index)
    {
        const FRuntimePartitionStreamingData* Data = reinterpret_cast<const FRuntimePartitionStreamingData*>(Helper.GetRawPtr(Index));
        const int32 Range = Data->GetLoadingRange();
        Maximum = FMath::Max(Maximum, Range);
        TSharedRef<FJsonObject> Entry = MakeShared<FJsonObject>();
        Entry->SetNumberField(TEXT("loading_range_cm"), Range);
        Entry->SetNumberField(TEXT("index"), Index);
        Result.Add(MakeShared<FJsonValueObject>(Entry));
    }
    return Result;
}
}

class FXinyiHostStreamingProbeModule final : public IModuleInterface
{
public:
    virtual void StartupModule() override
    {
        if (!FParse::Value(FCommandLine::Get(), TEXT("XinyiHostRoute="), RoutePath)) return;
        FParse::Value(FCommandLine::Get(), TEXT("XinyiHostManifest="), ManifestPath);
        FParse::Value(FCommandLine::Get(), TEXT("XinyiHostOutput="), OutputPath);
        FParse::Value(FCommandLine::Get(), TEXT("XinyiHostRunId="), RunId);
        StartedAt = FPlatformTime::Seconds();
        Report = MakeShared<FJsonObject>();
        Report->SetStringField(TEXT("schema"), TEXT("xinyi-runtime-engine-observation/v1"));
        Report->SetStringField(TEXT("run_id"), RunId);
        Report->SetStringField(TEXT("world"), XinyiHostProbe::WorldPath);
        Report->SetStringField(TEXT("status"), TEXT("INCOMPLETE"));
        Report->SetStringField(TEXT("process_id"), FString::FromInt(FPlatformProcess::GetCurrentProcessId()));
        Report->SetStringField(TEXT("world_type"), TEXT("Game"));
        Report->SetArrayField(TEXT("points"), {});
        if (!LoadInputs())
        {
            Finish(TEXT("FAIL_INPUT"));
            return;
        }
        TickHandle = FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateRaw(this, &FXinyiHostStreamingProbeModule::Tick));
    }

    virtual void ShutdownModule() override
    {
        if (TickHandle.IsValid()) FTSTicker::GetCoreTicker().RemoveTicker(TickHandle);
    }

private:
    bool LoadInputs()
    {
        if (RoutePath.IsEmpty() || ManifestPath.IsEmpty() || OutputPath.IsEmpty() || RunId.IsEmpty() ||
            IFileManager::Get().FileExists(*OutputPath)) return false;
        const TSharedPtr<FJsonObject> Route = XinyiHostProbe::ReadJson(RoutePath);
        const TSharedPtr<FJsonObject> Manifest = XinyiHostProbe::ReadJson(ManifestPath);
        if (!Route || !Manifest || Route->GetStringField(TEXT("world")) != XinyiHostProbe::WorldPath ||
            Route->GetStringField(TEXT("status")) != TEXT("PLAN_ONLY") ||
            Manifest->GetStringField(TEXT("status")) != TEXT("PASS_RUNTIME_WORLD")) return false;
        const TArray<TSharedPtr<FJsonValue>>* RoutePoints = nullptr;
        const TSharedPtr<FJsonObject>* Streaming = nullptr;
        const TArray<TSharedPtr<FJsonValue>>* Actors = nullptr;
        if (!Route->TryGetObjectField(TEXT("streaming"), Streaming) ||
            !(*Streaming)->TryGetArrayField(TEXT("route"), RoutePoints) || RoutePoints->Num() != 27 ||
            !Manifest->TryGetArrayField(TEXT("actors"), Actors) || Actors->Num() != 25) return false;
        TimeoutSeconds = (*Streaming)->GetNumberField(TEXT("timeout_seconds"));
        DwellSeconds = (*Streaming)->GetNumberField(TEXT("dwell_seconds"));
        for (const TSharedPtr<FJsonValue>& Value : *RoutePoints)
        {
            const TSharedPtr<FJsonObject> Row = Value->AsObject();
            if (!Row) return false;
            const TArray<TSharedPtr<FJsonValue>>* Position = nullptr;
            if (!Row->TryGetArrayField(TEXT("location_cm"), Position) || Position->Num() != 3) return false;
            XinyiHostProbe::FPoint Point;
            Point.Id = Row->GetStringField(TEXT("id"));
            Point.Kind = Row->GetStringField(TEXT("kind"));
            Point.ExpectedTile = Point.Kind == TEXT("tile") ? Row->GetStringField(TEXT("expected_tile_id")) : FString();
            Point.Location = FVector((*Position)[0]->AsNumber(), (*Position)[1]->AsNumber(), (*Position)[2]->AsNumber());
            Points.Add(MoveTemp(Point));
        }
        for (const TSharedPtr<FJsonValue>& Value : *Actors)
        {
            const TSharedPtr<FJsonObject> Row = Value->AsObject();
            if (!Row) return false;
            const TArray<TSharedPtr<FJsonValue>>* Position = nullptr;
            if (!Row->TryGetArrayField(TEXT("translation_cm"), Position) || Position->Num() != 3) return false;
            XinyiHostProbe::FTile Tile;
            Tile.Id = Row->GetStringField(TEXT("tile"));
            Tile.ExpectedLocation = FVector((*Position)[0]->AsNumber(), (*Position)[1]->AsNumber(), (*Position)[2]->AsNumber());
            const FString Asset = Row->GetStringField(TEXT("asset_path"));
            if (Tile.Id.IsEmpty() || Asset.IsEmpty() || TileByAsset.Contains(Asset)) return false;
            TileByAsset.Add(Asset, MoveTemp(Tile));
        }
        Report->SetStringField(TEXT("route_path"), RoutePath);
        Report->SetStringField(TEXT("manifest_path"), ManifestPath);
        return Points.Num() == 27 && TileByAsset.Num() == 25 && TimeoutSeconds > 0 && DwellSeconds >= 0;
    }

    bool Tick(float DeltaSeconds)
    {
        const double Now = FPlatformTime::Seconds();
        if (LastTick > 0) MaxTickMs = FMath::Max(MaxTickMs, (Now - LastTick) * 1000.0);
        LastTick = Now;
        if (!World)
        {
            for (const FWorldContext& Context : GEngine->GetWorldContexts())
            {
                UWorld* Candidate = Context.World();
                if (Context.WorldType == EWorldType::Game && Candidate && Candidate->HasBegunPlay() &&
                    Candidate->GetOutermost()->GetName() == XinyiHostProbe::WorldPath)
                {
                    World = Candidate;
                    break;
                }
            }
            if (!World)
            {
                if (Now - StartedAt > 90.0) Finish(TEXT("FAIL_WORLD_NOT_STARTED"));
                return !Finished;
            }
            if (!InitializeWorld())
            {
                Finish(TEXT("FAIL_WORLD_SETUP"));
                return false;
            }
        }
        if (Index >= Points.Num())
        {
            Finish(TEXT("ENGINE_ROUTE_COMPLETE"));
            return false;
        }
        const XinyiHostProbe::FPoint& Point = Points[Index];
        if (!Moving)
        {
            for (TActorIterator<APlayerController> It(World); It; ++It) It->bEnableStreamingSource = false;
            SourceActor->SetActorLocation(Point.Location);
            Source->EnableStreamingSource();
            StepStart = Now;
            CompleteSince = 0;
            MaxTickMs = 0;
            Moving = true;
            UE_LOG(LogTemp, Display, TEXT("XINYI_HOST_MOVE %s %.0f %.0f %.0f"), *Point.Id, Point.Location.X, Point.Location.Y, Point.Location.Z);
            return true;
        }
        bool Observed = false;
        for (const FWorldPartitionStreamingSource& RuntimeSource : Partition->GetStreamingSources())
        {
            if (FVector::Distance(RuntimeSource.Location, Point.Location) <= 1.0 &&
                RuntimeSource.TargetState == EStreamingSourceTargetState::Activated) Observed = true;
        }
        const bool Complete = Observed && Source->IsStreamingCompleted() && Subsystem->IsAllStreamingCompleted();
        CompleteSince = Complete ? (CompleteSince == 0 ? Now : CompleteSince) : 0;
        if (CompleteSince != 0 && Now - CompleteSince >= DwellSeconds)
        {
            Capture(Point, true, (Now - StepStart) * 1000.0);
            ++Index;
            Moving = false;
        }
        else if (Now - StepStart > TimeoutSeconds)
        {
            Capture(Point, false, (Now - StepStart) * 1000.0);
            Finish(TEXT("FAIL_STEP_TIMEOUT"));
            return false;
        }
        return true;
    }

    bool InitializeWorld()
    {
        Partition = World->GetWorldPartition();
        Subsystem = World->GetSubsystem<UWorldPartitionSubsystem>();
        Hash = XinyiHostProbe::GetHash(Partition);
        if (!Partition || !Subsystem || !Hash || !Partition->CanStream() || !Partition->IsStreamingEnabled()) return false;
        int32 Maximum = 0;
        Report->SetArrayField(TEXT("runtime_loading_ranges"), XinyiHostProbe::LoadingRanges(Hash, Maximum));
        Report->SetNumberField(TEXT("max_loading_range_cm"), Maximum);
        Report->SetBoolField(TEXT("far_control_distance_certified"), Maximum > 0 &&
            static_cast<double>(Maximum) < 500000.0);
        Report->SetStringField(TEXT("runtime_hash_class"), Hash->GetClass()->GetName());
        Report->SetBoolField(TEXT("can_stream"), Partition->CanStream());
        Report->SetBoolField(TEXT("streaming_enabled"), Partition->IsStreamingEnabled());
        for (TActorIterator<APlayerController> It(World); It; ++It) It->bEnableStreamingSource = false;
        FActorSpawnParameters Spawn;
        Spawn.Name = TEXT("XinyiHostTransientProbe");
        Spawn.ObjectFlags |= RF_Transient;
        SourceActor = World->SpawnActor<AActor>(Points[0].Location, FRotator::ZeroRotator, Spawn);
        if (!SourceActor) return false;
        USceneComponent* Root = NewObject<USceneComponent>(SourceActor, TEXT("XinyiHostRoot"), RF_Transient);
        SourceActor->AddInstanceComponent(Root);
        SourceActor->SetRootComponent(Root);
        Root->RegisterComponent();
        Source = NewObject<UWorldPartitionStreamingSourceComponent>(SourceActor, TEXT("XinyiHostStreamingSource"), RF_Transient);
        Source->TargetState = EStreamingSourceTargetState::Activated;
        SourceActor->AddInstanceComponent(Source);
        Source->RegisterComponent();
        Source->DisableStreamingSource();
        return Subsystem->IsStreamingSourceProviderRegistered(Source);
    }

    void Capture(const XinyiHostProbe::FPoint& Point, bool Complete, double WaitMs)
    {
        TSharedRef<FJsonObject> Row = MakeShared<FJsonObject>();
        Row->SetStringField(TEXT("id"), Point.Id);
        Row->SetStringField(TEXT("kind"), Point.Kind);
        Row->SetStringField(TEXT("expected_tile_id"), Point.ExpectedTile);
        Row->SetArrayField(TEXT("location_cm"), XinyiHostProbe::VectorJson(SourceActor->GetActorLocation()));
        Row->SetStringField(TEXT("requested_state"), TEXT("Activated"));
        Row->SetBoolField(TEXT("source_enabled"), Source->IsStreamingSourceEnabled());
        Row->SetBoolField(TEXT("source_registered"), Subsystem->IsStreamingSourceProviderRegistered(Source));
        Row->SetBoolField(TEXT("streaming_completed"), Complete);
        Row->SetNumberField(TEXT("wait_ms"), WaitMs);
        Row->SetNumberField(TEXT("hitch_ms"), MaxTickMs);
        Row->SetNumberField(TEXT("active_source_count"), Partition->GetStreamingSources().Num());
        bool Observed = false;
        TArray<TSharedPtr<FJsonValue>> ActiveSources;
        for (const FWorldPartitionStreamingSource& RuntimeSource : Partition->GetStreamingSources())
        {
            TSharedRef<FJsonObject> SourceRow = MakeShared<FJsonObject>();
            SourceRow->SetStringField(TEXT("name"), RuntimeSource.Name.ToString());
            SourceRow->SetArrayField(TEXT("location_cm"), XinyiHostProbe::VectorJson(RuntimeSource.Location));
            ActiveSources.Add(MakeShared<FJsonValueObject>(SourceRow));
            if (FVector::Distance(RuntimeSource.Location, Point.Location) <= 1.0 &&
                RuntimeSource.TargetState == EStreamingSourceTargetState::Activated) Observed = true;
        }
        Row->SetBoolField(TEXT("source_observed"), Observed);
        Row->SetArrayField(TEXT("active_sources"), ActiveSources);
        TSet<FString> Cells;
        TSet<FString> ActiveCells;
        TSet<FString> TerrainCells;
        Hash->ForEachStreamingCells([&](const UWorldPartitionRuntimeCell* Cell)
        {
            const EWorldPartitionRuntimeCellState State = Cell->GetCurrentState();
            if (State >= EWorldPartitionRuntimeCellState::Loaded)
            {
                Cells.Add(Cell->GetName());
                if (State == EWorldPartitionRuntimeCellState::Activated) ActiveCells.Add(Cell->GetName());
                for (FName ActorName : Cell->GetActors())
                    if (ActorName.ToString().Contains(TEXT("LandscapeStreamingProxy"))) TerrainCells.Add(Cell->GetName());
            }
            return true;
        });
        Row->SetNumberField(TEXT("loaded_cell_count"), Cells.Num());
        Row->SetArrayField(TEXT("loaded_cell_names"), XinyiHostProbe::StringsJson(Cells));
        Row->SetArrayField(TEXT("active_cell_names"), XinyiHostProbe::StringsJson(ActiveCells));
        Row->SetArrayField(TEXT("terrain_cell_names"), XinyiHostProbe::StringsJson(TerrainCells));
        TSet<FString> Tiles;
        TSet<FString> Missing;
        double Drift = 0;
        for (TActorIterator<AStaticMeshActor> It(World); It; ++It)
        {
            UStaticMesh* Mesh = It->GetStaticMeshComponent() ? It->GetStaticMeshComponent()->GetStaticMesh() : nullptr;
            if (!Mesh)
            {
                Missing.Add(It->GetName() + TEXT(":null_static_mesh"));
                continue;
            }
            const XinyiHostProbe::FTile* Expected = TileByAsset.Find(Mesh->GetPathName());
            if (!Expected) continue;
            if (Tiles.Contains(Expected->Id)) Missing.Add(Expected->Id + TEXT(":duplicate_loaded_actor"));
            Tiles.Add(Expected->Id);
            Drift = FMath::Max(Drift, FVector::Distance(It->GetActorLocation(), Expected->ExpectedLocation));
        }
        TSet<FString> Loaded;
        TSet<FString> Unloaded;
        for (const FString& Tile : Tiles) if (!PreviousTiles.Contains(Tile)) Loaded.Add(Tile);
        for (const FString& Tile : PreviousTiles) if (!Tiles.Contains(Tile)) Unloaded.Add(Tile);
        Row->SetArrayField(TEXT("loaded_tile_ids"), XinyiHostProbe::StringsJson(Tiles));
        Row->SetNumberField(TEXT("loaded_actor_count"), Tiles.Num());
        Row->SetArrayField(TEXT("load_delta"), XinyiHostProbe::StringsJson(Loaded));
        Row->SetArrayField(TEXT("unload_delta"), XinyiHostProbe::StringsJson(Unloaded));
        Row->SetNumberField(TEXT("placement_max_error_cm"), Drift);
        Row->SetArrayField(TEXT("missing_refs"), XinyiHostProbe::StringsJson(Missing));
        Row->SetArrayField(TEXT("errors"), {});
        PreviousTiles = MoveTemp(Tiles);
        TSharedRef<FJsonObject> Terrain = MakeShared<FJsonObject>();
        int32 Roots = 0, Proxies = 0, Render = 0, Collision = 0;
        for (TActorIterator<ALandscapeProxy> It(World); It; ++It)
        {
            if (It->IsA<ALandscapeStreamingProxy>()) ++Proxies; else ++Roots;
            TArray<ULandscapeComponent*> RenderComponents;
            TArray<ULandscapeHeightfieldCollisionComponent*> CollisionComponents;
            It->GetComponents(RenderComponents);
            It->GetComponents(CollisionComponents);
            Render += RenderComponents.Num();
            Collision += CollisionComponents.Num();
        }
        Terrain->SetNumberField(TEXT("root_actor_count"), Roots);
        Terrain->SetNumberField(TEXT("proxy_actor_count"), Proxies);
        Terrain->SetNumberField(TEXT("render_component_count"), Render);
        Terrain->SetNumberField(TEXT("collision_component_count"), Collision);
        Terrain->SetNumberField(TEXT("loaded_cell_count"), TerrainCells.Num());
        Row->SetObjectField(TEXT("terrain"), Terrain);
        TArray<TSharedPtr<FJsonValue>> Rows = Report->GetArrayField(TEXT("points"));
        Rows.Add(MakeShared<FJsonValueObject>(Row));
        Report->SetArrayField(TEXT("points"), Rows);
        UE_LOG(LogTemp, Display, TEXT("XINYI_HOST_POINT %s tiles=%d cells=%d terrain_proxies=%d complete=%s wait_ms=%.0f"),
            *Point.Id, PreviousTiles.Num(), Cells.Num(), Proxies, Complete ? TEXT("true") : TEXT("false"), WaitMs);
    }

    void Finish(const TCHAR* Status)
    {
        if (Finished) return;
        Finished = true;
        if (Report)
        {
            Report->SetStringField(TEXT("status"), Status);
            FString Body;
            FJsonSerializer::Serialize(Report.ToSharedRef(), TJsonWriterFactory<>::Create(&Body));
            if (!OutputPath.IsEmpty() && !IFileManager::Get().FileExists(*OutputPath))
            {
                IFileManager::Get().MakeDirectory(*FPaths::GetPath(OutputPath), true);
                FFileHelper::SaveStringToFile(Body, *OutputPath);
            }
        }
        if (SourceActor) SourceActor->Destroy();
        UE_LOG(LogTemp, Display, TEXT("XINYI_HOST_FINISH %s output=%s"), Status, *OutputPath);
        FPlatformMisc::RequestExit(false);
    }

    FTSTicker::FDelegateHandle TickHandle;
    FString RoutePath, ManifestPath, OutputPath, RunId;
    TArray<XinyiHostProbe::FPoint> Points;
    TMap<FString, XinyiHostProbe::FTile> TileByAsset;
    TSharedPtr<FJsonObject> Report;
    TSet<FString> PreviousTiles;
    UWorld* World = nullptr;
    UWorldPartition* Partition = nullptr;
    UWorldPartitionSubsystem* Subsystem = nullptr;
    UWorldPartitionRuntimeHash* Hash = nullptr;
    AActor* SourceActor = nullptr;
    UWorldPartitionStreamingSourceComponent* Source = nullptr;
    int32 Index = 0;
    bool Moving = false, Finished = false;
    double TimeoutSeconds = 0, DwellSeconds = 0, StartedAt = 0, StepStart = 0, CompleteSince = 0;
    double LastTick = 0, MaxTickMs = 0;
};

IMPLEMENT_MODULE(FXinyiHostStreamingProbeModule, XinyiHostStreamingProbe)
