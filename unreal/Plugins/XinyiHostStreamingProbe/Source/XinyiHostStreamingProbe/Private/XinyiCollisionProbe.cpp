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
#include "PhysicsEngine/BodySetup.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "WorldPartition/WorldPartition.h"
#include "WorldPartition/WorldPartitionSubsystem.h"

namespace
{
constexpr TCHAR WorldPath[] = TEXT("/Game/XinyiV2/L_XinyiV2_Contract_WP");

TArray<TSharedPtr<FJsonValue>> Vec(const FVector& P)
{
    return {MakeShared<FJsonValueNumber>(P.X), MakeShared<FJsonValueNumber>(P.Y), MakeShared<FJsonValueNumber>(P.Z)};
}

FVector ReadVec(const TArray<TSharedPtr<FJsonValue>>& A)
{
    return FVector(A[0]->AsNumber(), A[1]->AsNumber(), A[2]->AsNumber());
}

TSharedPtr<FJsonObject> ReadFile(const FString& Path)
{
    FString Body;
    TSharedPtr<FJsonObject> Object;
    return FFileHelper::LoadFileToString(Body, *Path) &&
        FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Body), Object) ? Object : nullptr;
}

TArray<TSharedPtr<FJsonValue>> StringSet(const TSet<FString>& Input)
{
    TArray<FString> Sorted = Input.Array();
    Sorted.Sort();
    TArray<TSharedPtr<FJsonValue>> Result;
    for (const FString& S : Sorted) Result.Add(MakeShared<FJsonValueString>(S));
    return Result;
}

struct FStep
{
    FString Id;
    FString Kind;
    FVector Source;
    TArray<TSharedPtr<FJsonValue>> Terrain;
    TArray<TSharedPtr<FJsonValue>> Buildings;
};

class FCollisionProbe
{
public:
    bool Start()
    {
        FParse::Value(FCommandLine::Get(), TEXT("XinyiCollisionPlan="), PlanPath);
        FParse::Value(FCommandLine::Get(), TEXT("XinyiCollisionManifest="), ManifestPath);
        FParse::Value(FCommandLine::Get(), TEXT("XinyiCollisionOutput="), OutputPath);
        FParse::Value(FCommandLine::Get(), TEXT("XinyiCollisionRunId="), RunId);
        StartedAt = FPlatformTime::Seconds();
        Report = MakeShared<FJsonObject>();
        Report->SetStringField(TEXT("schema"), TEXT("xinyi-packaged-collision-observation/v1"));
        Report->SetStringField(TEXT("status"), TEXT("INCOMPLETE"));
        Report->SetStringField(TEXT("run_id"), RunId);
        Report->SetStringField(TEXT("world"), WorldPath);
        Report->SetNumberField(TEXT("process_id"), FPlatformProcess::GetCurrentProcessId());
        Report->SetStringField(TEXT("trace_channel"), TEXT("ECC_Visibility"));
        Report->SetBoolField(TEXT("primary_trace_complex"), false);
        Report->SetBoolField(TEXT("reference_trace_complex"), true);
        Report->SetArrayField(TEXT("steps"), {});
        Report->SetArrayField(TEXT("building_policy"), {});
        if (!LoadInputs()) { Finish(TEXT("FAIL_INPUT")); return false; }
        Handle = FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateRaw(this, &FCollisionProbe::Tick));
        return true;
    }

    ~FCollisionProbe()
    {
        if (Handle.IsValid()) FTSTicker::GetCoreTicker().RemoveTicker(Handle);
    }

private:
    bool LoadInputs()
    {
        if (PlanPath.IsEmpty() || ManifestPath.IsEmpty() || OutputPath.IsEmpty() || RunId.IsEmpty() ||
            IFileManager::Get().FileExists(*OutputPath)) return false;
        TSharedPtr<FJsonObject> Plan = ReadFile(PlanPath);
        TSharedPtr<FJsonObject> Manifest = ReadFile(ManifestPath);
        if (!Plan || !Manifest || Plan->GetStringField(TEXT("status")) != TEXT("PLAN_ONLY") ||
            Plan->GetStringField(TEXT("world")) != WorldPath ||
            Manifest->GetStringField(TEXT("status")) != TEXT("PASS_RUNTIME_WORLD")) return false;
        const TArray<TSharedPtr<FJsonValue>>* Rows = nullptr;
        const TArray<TSharedPtr<FJsonValue>>* Actors = nullptr;
        if (!Plan->TryGetArrayField(TEXT("steps"), Rows) || Rows->Num() < 60 ||
            !Manifest->TryGetArrayField(TEXT("actors"), Actors) || Actors->Num() != 25) return false;
        for (const auto& Value : *Rows)
        {
            const TSharedPtr<FJsonObject> Row = Value->AsObject();
            const TArray<TSharedPtr<FJsonValue>>* SourceValue = nullptr;
            const TArray<TSharedPtr<FJsonValue>>* TerrainValue = nullptr;
            const TArray<TSharedPtr<FJsonValue>>* BuildingValue = nullptr;
            if (!Row || !Row->TryGetArrayField(TEXT("source_cm"), SourceValue) || SourceValue->Num()!=3 ||
                !Row->TryGetArrayField(TEXT("terrain_samples"), TerrainValue) ||
                !Row->TryGetArrayField(TEXT("building_samples"), BuildingValue)) return false;
            FStep Step;
            Step.Id = Row->GetStringField(TEXT("id"));
            Step.Kind = Row->GetStringField(TEXT("kind"));
            Step.Source = ReadVec(*SourceValue);
            Step.Terrain = *TerrainValue;
            Step.Buildings = *BuildingValue;
            Steps.Add(MoveTemp(Step));
        }
        for (const auto& Value : *Actors)
        {
            const TSharedPtr<FJsonObject> Row = Value->AsObject();
            if (!Row) return false;
            const FString Asset = Row->GetStringField(TEXT("asset_path"));
            const FString Tile = Row->GetStringField(TEXT("tile"));
            if (Asset.IsEmpty() || Tile.IsEmpty() || TileByAsset.Contains(Asset)) return false;
            TileByAsset.Add(Asset, Tile);
        }
        Report->SetNumberField(TEXT("plan_step_count"), Steps.Num());
        Report->SetNumberField(TEXT("terrain_tolerance_cm"), Plan->GetNumberField(TEXT("terrain_tolerance_cm")));
        return Steps.Num() >= 60 && TileByAsset.Num()==25;
    }

    bool Tick(float)
    {
        const double Now = FPlatformTime::Seconds();
        if (!World)
        {
            for (const FWorldContext& C : GEngine->GetWorldContexts())
            {
                UWorld* Candidate = C.World();
                if (C.WorldType == EWorldType::Game && Candidate && Candidate->HasBegunPlay() &&
                    Candidate->GetOutermost()->GetName() == WorldPath) { World = Candidate; break; }
            }
            if (!World)
            {
                if (Now - StartedAt > 90) Finish(TEXT("FAIL_WORLD_NOT_STARTED"));
                return !Finished;
            }
            if (!InitializeWorld()) { Finish(TEXT("FAIL_WORLD_SETUP")); return false; }
        }
        if (Index >= Steps.Num()) { Finish(TEXT("ENGINE_COLLISION_ROUTE_COMPLETE")); return false; }
        const FStep& Step = Steps[Index];
        if (!Moving)
        {
            SourceActor->SetActorLocation(Step.Source);
            Source->EnableStreamingSource();
            StepAt = Now;
            CompleteSince = 0;
            Moving = true;
            UE_LOG(LogTemp, Display, TEXT("XINYI_COLLISION_MOVE %s"), *Step.Id);
            return true;
        }
        bool Observed = false;
        for (const FWorldPartitionStreamingSource& RuntimeSource : Partition->GetStreamingSources())
            if (FVector::Distance(RuntimeSource.Location, Step.Source) <= 1.0 &&
                RuntimeSource.TargetState == EStreamingSourceTargetState::Activated) Observed = true;
        const bool Complete = Observed && Source->IsStreamingCompleted() && Subsystem->IsAllStreamingCompleted();
        CompleteSince = Complete ? (CompleteSince == 0 ? Now : CompleteSince) : 0;
        if (CompleteSince && Now - CompleteSince >= 0.25)
        {
            Capture(Step, true, (Now-StepAt)*1000.0);
            ++Index; Moving = false;
        }
        else if (Now-StepAt > 90.0)
        {
            Capture(Step, false, (Now-StepAt)*1000.0);
            Finish(TEXT("FAIL_STEP_TIMEOUT"));
            return false;
        }
        return true;
    }

    bool InitializeWorld()
    {
        Partition = World->GetWorldPartition();
        Subsystem = World->GetSubsystem<UWorldPartitionSubsystem>();
        if (!Partition || !Subsystem || !Partition->CanStream() || !Partition->IsStreamingEnabled()) return false;
        for (TActorIterator<APlayerController> It(World); It; ++It) It->bEnableStreamingSource = false;
        FActorSpawnParameters Spawn;
        Spawn.Name = TEXT("XinyiCollisionTransientSource");
        Spawn.ObjectFlags |= RF_Transient;
        SourceActor = World->SpawnActor<AActor>(Steps[0].Source, FRotator::ZeroRotator, Spawn);
        if (!SourceActor) return false;
        USceneComponent* Root = NewObject<USceneComponent>(SourceActor, TEXT("CollisionSourceRoot"), RF_Transient);
        SourceActor->AddInstanceComponent(Root);
        SourceActor->SetRootComponent(Root);
        Root->RegisterComponent();
        Source = NewObject<UWorldPartitionStreamingSourceComponent>(SourceActor, TEXT("CollisionStreamingSource"), RF_Transient);
        Source->TargetState = EStreamingSourceTargetState::Activated;
        SourceActor->AddInstanceComponent(Source);
        Source->RegisterComponent();
        Source->DisableStreamingSource();
        return Subsystem->IsStreamingSourceProviderRegistered(Source);
    }

    void AuditBuildings(TSet<FString>& Loaded)
    {
        for (TActorIterator<AStaticMeshActor> It(World); It; ++It)
        {
            UStaticMeshComponent* Component = It->GetStaticMeshComponent();
            UStaticMesh* Mesh = Component ? Component->GetStaticMesh() : nullptr;
            if (!Mesh) continue;
            const FString* Tile = TileByAsset.Find(Mesh->GetPathName());
            if (!Tile) continue;
            Loaded.Add(*Tile);
            if (Audited.Contains(*Tile)) continue;
            Audited.Add(*Tile);
            UBodySetup* Body = Mesh->GetBodySetup();
            TSharedRef<FJsonObject> Row = MakeShared<FJsonObject>();
            Row->SetStringField(TEXT("tile"), *Tile);
            Row->SetStringField(TEXT("asset_path"), Mesh->GetPathName());
            Row->SetStringField(TEXT("actor_package"), It->GetPackage()->GetName());
            Row->SetStringField(TEXT("runtime_ownership_note"), TEXT("actor observed loaded by World Partition; editor-only spatial/grid properties are not exposed by the packaged AActor API"));
            Row->SetNumberField(TEXT("component_collision_enabled_enum"), static_cast<int32>(Component->GetCollisionEnabled()));
            Row->SetNumberField(TEXT("visibility_response_enum"), static_cast<int32>(Component->GetCollisionResponseToChannel(ECC_Visibility)));
            Row->SetStringField(TEXT("body_setup"), Body ? Body->GetPathName() : TEXT(""));
            Row->SetStringField(TEXT("body_guid"), Body ? Body->BodySetupGuid.ToString() : TEXT(""));
            Row->SetNumberField(TEXT("trace_flag_enum"), Body ? static_cast<int32>(Body->GetCollisionTraceFlag().GetValue()) : -1);
            if (Body)
            {
                Row->SetNumberField(TEXT("sphere_count"), Body->AggGeom.SphereElems.Num());
                Row->SetNumberField(TEXT("box_count"), Body->AggGeom.BoxElems.Num());
                Row->SetNumberField(TEXT("capsule_count"), Body->AggGeom.SphylElems.Num());
                Row->SetNumberField(TEXT("tapered_capsule_count"), Body->AggGeom.TaperedCapsuleElems.Num());
                Row->SetNumberField(TEXT("convex_count"), Body->AggGeom.ConvexElems.Num());
                Row->SetNumberField(TEXT("body_resource_bytes"), Body->GetResourceSizeBytes(EResourceSizeMode::Exclusive));
            }
            Row->SetNumberField(TEXT("mesh_resource_bytes"), Mesh->GetResourceSizeBytes(EResourceSizeMode::Exclusive));
            Policies.Add(MakeShared<FJsonValueObject>(Row));
        }
    }

    TSharedRef<FJsonObject> HitInfo(const FHitResult& Hit, bool DidHit)
    {
        TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
        Result->SetBoolField(TEXT("hit"), DidHit);
        if (DidHit)
        {
            const AActor* Actor = Hit.GetActor();
            const UPrimitiveComponent* Component = Hit.GetComponent();
            Result->SetStringField(TEXT("actor"), Actor ? Actor->GetPathName() : TEXT(""));
            Result->SetStringField(TEXT("actor_class"), Actor ? Actor->GetClass()->GetName() : TEXT(""));
            Result->SetStringField(TEXT("component"), Component ? Component->GetPathName() : TEXT(""));
            Result->SetStringField(TEXT("component_class"), Component ? Component->GetClass()->GetName() : TEXT(""));
            Result->SetArrayField(TEXT("location_cm"), Vec(Hit.Location));
            Result->SetNumberField(TEXT("distance_cm"), Hit.Distance);
            FString Tile;
            if (const AStaticMeshActor* StaticActor = Cast<AStaticMeshActor>(Actor))
                if (UStaticMesh* Mesh = StaticActor->GetStaticMeshComponent()->GetStaticMesh())
                    if (const FString* Found = TileByAsset.Find(Mesh->GetPathName())) Tile = *Found;
            Result->SetStringField(TEXT("building_tile"), Tile);
            Result->SetBoolField(TEXT("is_landscape"), Actor && Actor->IsA<ALandscapeProxy>() &&
                Component && Component->IsA<ULandscapeHeightfieldCollisionComponent>());
        }
        return Result;
    }

    void Capture(const FStep& Step, bool Complete, double WaitMs)
    {
        TSharedRef<FJsonObject> Row = MakeShared<FJsonObject>();
        Row->SetStringField(TEXT("id"), Step.Id);
        Row->SetStringField(TEXT("kind"), Step.Kind);
        Row->SetArrayField(TEXT("source_cm"), Vec(SourceActor->GetActorLocation()));
        Row->SetBoolField(TEXT("streaming_completed"), Complete);
        Row->SetNumberField(TEXT("wait_ms"), WaitMs);
        TSet<FString> Loaded;
        AuditBuildings(Loaded);
        Row->SetArrayField(TEXT("loaded_tiles"), StringSet(Loaded));
        TArray<TSharedPtr<FJsonValue>> TerrainActors;
        int32 TerrainRender = 0, TerrainCollision = 0;
        for (TActorIterator<ALandscapeProxy> It(World); It; ++It)
        {
            TArray<ULandscapeComponent*> Render;
            TArray<ULandscapeHeightfieldCollisionComponent*> Collision;
            It->GetComponents(Render); It->GetComponents(Collision);
            TerrainRender += Render.Num(); TerrainCollision += Collision.Num();
            TSharedRef<FJsonObject> Owner = MakeShared<FJsonObject>();
            Owner->SetStringField(TEXT("actor"), It->GetPathName());
            Owner->SetStringField(TEXT("package"), It->GetPackage()->GetName());
            Owner->SetBoolField(TEXT("is_proxy"), It->IsA<ALandscapeStreamingProxy>());
            Owner->SetStringField(TEXT("runtime_ownership_note"), TEXT("proxy presence and package identity observed; editor-only spatial/grid properties unavailable in packaged AActor API"));
            Owner->SetNumberField(TEXT("render_count"), Render.Num());
            Owner->SetNumberField(TEXT("collision_count"), Collision.Num());
            TArray<TSharedPtr<FJsonValue>> Components;
            for (const auto* C : Collision)
            {
                TSharedRef<FJsonObject> ComponentRow = MakeShared<FJsonObject>();
                ComponentRow->SetStringField(TEXT("name"), C->GetPathName());
                ComponentRow->SetNumberField(TEXT("collision_enabled_enum"), static_cast<int32>(C->GetCollisionEnabled()));
                ComponentRow->SetNumberField(TEXT("visibility_response_enum"), static_cast<int32>(C->GetCollisionResponseToChannel(ECC_Visibility)));
                Components.Add(MakeShared<FJsonValueObject>(ComponentRow));
            }
            Owner->SetArrayField(TEXT("collision_components"), Components);
            TerrainActors.Add(MakeShared<FJsonValueObject>(Owner));
        }
        Row->SetArrayField(TEXT("terrain_actors"), TerrainActors);
        Row->SetNumberField(TEXT("terrain_render_count"), TerrainRender);
        Row->SetNumberField(TEXT("terrain_collision_count"), TerrainCollision);
        TArray<TSharedPtr<FJsonValue>> TerrainResults;
        for (const auto& Value : Step.Terrain)
        {
            const TSharedPtr<FJsonObject> Sample = Value->AsObject();
            const auto& XY = Sample->GetArrayField(TEXT("xy_cm"));
            const double X=XY[0]->AsNumber(), Y=XY[1]->AsNumber();
            FCollisionQueryParams Params(SCENE_QUERY_STAT(XinyiTerrainCollision), false);
            FCollisionQueryParams ComplexParams(SCENE_QUERY_STAT(XinyiTerrainCollisionComplex), true);
            for (TActorIterator<AStaticMeshActor> It(World); It; ++It) Params.AddIgnoredActor(*It);
            for (TActorIterator<AStaticMeshActor> It(World); It; ++It) ComplexParams.AddIgnoredActor(*It);
            FHitResult Hit;
            const bool DidHit=World->LineTraceSingleByChannel(Hit,FVector(X,Y,30000),FVector(X,Y,-1000),ECC_Visibility,Params);
            FHitResult ComplexHit;
            const bool DidHitComplex=World->LineTraceSingleByChannel(ComplexHit,FVector(X,Y,30000),FVector(X,Y,-1000),ECC_Visibility,ComplexParams);
            TSharedRef<FJsonObject> Result=HitInfo(Hit,DidHit);
            Result->SetBoolField(TEXT("trace_complex"),false);
            Result->SetObjectField(TEXT("complex_reference"),HitInfo(ComplexHit,DidHitComplex));
            Result->SetStringField(TEXT("id"),Sample->GetStringField(TEXT("id")));
            Result->SetStringField(TEXT("kind"),Sample->GetStringField(TEXT("kind")));
            Result->SetArrayField(TEXT("xy_cm"),{MakeShared<FJsonValueNumber>(X),MakeShared<FJsonValueNumber>(Y)});
            const bool Expected=Sample->GetBoolField(TEXT("expect_hit"));
            Result->SetBoolField(TEXT("expect_hit"),Expected);
            double ExpectedZ=0;
            if (Sample->TryGetNumberField(TEXT("expected_z_cm"),ExpectedZ))
            {
                Result->SetNumberField(TEXT("expected_z_cm"),ExpectedZ);
                if (DidHit) Result->SetNumberField(TEXT("absolute_z_error_cm"),FMath::Abs(Hit.Location.Z-ExpectedZ));
            }
            TerrainResults.Add(MakeShared<FJsonValueObject>(Result));
        }
        Row->SetArrayField(TEXT("terrain_traces"), TerrainResults);
        TArray<TSharedPtr<FJsonValue>> BuildingResults;
        for (const auto& Value : Step.Buildings)
        {
            const TSharedPtr<FJsonObject> Sample=Value->AsObject();
            const FVector Start=ReadVec(Sample->GetArrayField(TEXT("start_cm")));
            const FVector End=ReadVec(Sample->GetArrayField(TEXT("end_cm")));
            FCollisionQueryParams Params(SCENE_QUERY_STAT(XinyiBuildingCollision),false);
            FCollisionQueryParams ComplexParams(SCENE_QUERY_STAT(XinyiBuildingCollisionComplex),true);
            for (TActorIterator<ALandscapeProxy> It(World); It; ++It) Params.AddIgnoredActor(*It);
            for (TActorIterator<ALandscapeProxy> It(World); It; ++It) ComplexParams.AddIgnoredActor(*It);
            FHitResult Hit;
            const bool DidHit=World->LineTraceSingleByChannel(Hit,Start,End,ECC_Visibility,Params);
            FHitResult ComplexHit;
            const bool DidHitComplex=World->LineTraceSingleByChannel(ComplexHit,Start,End,ECC_Visibility,ComplexParams);
            TSharedRef<FJsonObject> Result=HitInfo(Hit,DidHit);
            Result->SetBoolField(TEXT("trace_complex"),false);
            Result->SetObjectField(TEXT("complex_reference"),HitInfo(ComplexHit,DidHitComplex));
            Result->SetStringField(TEXT("id"),Sample->GetStringField(TEXT("id")));
            Result->SetStringField(TEXT("kind"),Sample->GetStringField(TEXT("kind")));
            Result->SetStringField(TEXT("expected_tile"),Sample->GetStringField(TEXT("expected_tile")));
            Result->SetBoolField(TEXT("expect_hit"),Sample->GetBoolField(TEXT("expect_hit")));
            Result->SetArrayField(TEXT("start_cm"),Vec(Start));
            Result->SetArrayField(TEXT("end_cm"),Vec(End));
            BuildingResults.Add(MakeShared<FJsonValueObject>(Result));
        }
        Row->SetArrayField(TEXT("building_traces"),BuildingResults);
        TArray<TSharedPtr<FJsonValue>> All=Report->GetArrayField(TEXT("steps"));
        All.Add(MakeShared<FJsonValueObject>(Row)); Report->SetArrayField(TEXT("steps"),All);
        UE_LOG(LogTemp,Display,TEXT("XINYI_COLLISION_POINT %s terrain=%d building=%d tiles=%d wait_ms=%.0f"),
            *Step.Id,TerrainResults.Num(),BuildingResults.Num(),Loaded.Num(),WaitMs);
    }

    void Finish(const TCHAR* Status)
    {
        if (Finished) return;
        Finished=true;
        if (Report)
        {
            Report->SetStringField(TEXT("status"),Status);
            Report->SetArrayField(TEXT("building_policy"),Policies);
            Report->SetNumberField(TEXT("audited_tile_count"),Audited.Num());
            FString Body;
            FJsonSerializer::Serialize(Report.ToSharedRef(),TJsonWriterFactory<>::Create(&Body));
            if (!OutputPath.IsEmpty() && !IFileManager::Get().FileExists(*OutputPath))
            {
                IFileManager::Get().MakeDirectory(*FPaths::GetPath(OutputPath),true);
                FFileHelper::SaveStringToFile(Body,*OutputPath);
            }
        }
        if (SourceActor) SourceActor->Destroy();
        UE_LOG(LogTemp,Display,TEXT("XINYI_COLLISION_FINISH %s"),Status);
        FPlatformMisc::RequestExit(false);
    }

    FTSTicker::FDelegateHandle Handle;
    FString PlanPath,ManifestPath,OutputPath,RunId;
    TArray<FStep> Steps;
    TMap<FString,FString> TileByAsset;
    TSet<FString> Audited;
    TArray<TSharedPtr<FJsonValue>> Policies;
    TSharedPtr<FJsonObject> Report;
    UWorld* World=nullptr;
    UWorldPartition* Partition=nullptr;
    UWorldPartitionSubsystem* Subsystem=nullptr;
    AActor* SourceActor=nullptr;
    UWorldPartitionStreamingSourceComponent* Source=nullptr;
    int32 Index=0;
    bool Moving=false,Finished=false;
    double StartedAt=0,StepAt=0,CompleteSince=0;
};

TUniquePtr<FCollisionProbe> Probe;
}

void StartXinyiCollisionProbe()
{
    Probe=MakeUnique<FCollisionProbe>();
    Probe->Start();
}
