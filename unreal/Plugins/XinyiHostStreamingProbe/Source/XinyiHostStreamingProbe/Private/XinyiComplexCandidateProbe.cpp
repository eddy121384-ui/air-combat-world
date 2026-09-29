#include "XinyiCollisionDynamicProbe.h"

#include "Algo/Sort.h"
#include "Components/BoxComponent.h"
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
#include "HAL/PlatformProcess.h"
#include "LandscapeProxy.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "PhysicsEngine/BodySetup.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "WorldPartition/WorldPartition.h"
#include "WorldPartition/WorldPartitionSubsystem.h"

namespace XinyiComplexCandidate
{
constexpr TCHAR WorldPath[] = TEXT("/Game/XinyiV2/L_XinyiV2_Contract_WP");
constexpr int32 QueryRepetitions = 64;

TArray<TSharedPtr<FJsonValue>> Vec(const FVector& Value)
{
    return {MakeShared<FJsonValueNumber>(Value.X), MakeShared<FJsonValueNumber>(Value.Y), MakeShared<FJsonValueNumber>(Value.Z)};
}

FVector ReadVec(const TArray<TSharedPtr<FJsonValue>>& Value)
{
    return FVector(Value[0]->AsNumber(), Value[1]->AsNumber(), Value[2]->AsNumber());
}

TSharedPtr<FJsonObject> ReadJson(const FString& Path)
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
    for (const FString& Item : Sorted) Result.Add(MakeShared<FJsonValueString>(Item));
    return Result;
}

double Percentile(TArray<double> Values, double Fraction)
{
    if (Values.IsEmpty()) return 0.0;
    Values.Sort();
    const double Position = Fraction * static_cast<double>(Values.Num() - 1);
    const int32 Lower = FMath::FloorToInt(Position);
    const int32 Upper = FMath::CeilToInt(Position);
    return FMath::Lerp(Values[Lower], Values[Upper], Position - Lower);
}

struct FStep
{
    FString Id;
    FString Kind;
    FVector Source;
    TArray<TSharedPtr<FJsonValue>> Buildings;
};

class FProbe
{
public:
    bool Start()
    {
        FParse::Value(FCommandLine::Get(), TEXT("XinyiComplexCandidatePlan="), PlanPath);
        FParse::Value(FCommandLine::Get(), TEXT("XinyiComplexCandidateManifest="), ManifestPath);
        FParse::Value(FCommandLine::Get(), TEXT("XinyiComplexCandidateOutput="), OutputPath);
        FParse::Value(FCommandLine::Get(), TEXT("XinyiComplexCandidateRunId="), RunId);
        FParse::Value(FCommandLine::Get(), TEXT("XinyiComplexCandidateMode="), Mode);
        bCandidate = Mode == TEXT("ComplexAsSimple");
        if (!bCandidate && Mode != TEXT("Baseline")) return false;
        StartedAt = FPlatformTime::Seconds();
        Report = MakeShared<FJsonObject>();
        Report->SetStringField(TEXT("schema"), TEXT("xinyi-complex-as-simple-observation/v1"));
        Report->SetStringField(TEXT("status"), TEXT("INCOMPLETE"));
        Report->SetStringField(TEXT("run_id"), RunId);
        Report->SetStringField(TEXT("mode"), Mode);
        Report->SetStringField(TEXT("isolation"), TEXT("transient packaged-process BodySetup override plus component physics-state recreation; no package save"));
        Report->SetStringField(TEXT("world"), WorldPath);
        Report->SetNumberField(TEXT("process_id"), FPlatformProcess::GetCurrentProcessId());
        Report->SetBoolField(TEXT("primary_trace_complex"), false);
        Report->SetNumberField(TEXT("query_repetitions"), QueryRepetitions);
        Report->SetArrayField(TEXT("steps"), {});
        Report->SetArrayField(TEXT("building_policy"), {});
        if (!LoadInputs()) { Finish(TEXT("FAIL_INPUT")); return false; }
        Handle = FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateRaw(this, &FProbe::Tick));
        return true;
    }

    ~FProbe()
    {
        if (Handle.IsValid()) FTSTicker::GetCoreTicker().RemoveTicker(Handle);
    }

private:
    bool LoadInputs()
    {
        if (PlanPath.IsEmpty() || ManifestPath.IsEmpty() || OutputPath.IsEmpty() || RunId.IsEmpty() ||
            IFileManager::Get().FileExists(*OutputPath)) return false;
        const TSharedPtr<FJsonObject> Plan = ReadJson(PlanPath);
        const TSharedPtr<FJsonObject> Manifest = ReadJson(ManifestPath);
        if (!Plan || !Manifest || Plan->GetStringField(TEXT("status")) != TEXT("PLAN_ONLY") ||
            Plan->GetStringField(TEXT("world")) != WorldPath ||
            Manifest->GetStringField(TEXT("status")) != TEXT("PASS_RUNTIME_WORLD")) return false;
        const TArray<TSharedPtr<FJsonValue>>* PlanSteps = nullptr;
        const TArray<TSharedPtr<FJsonValue>>* Actors = nullptr;
        if (!Plan->TryGetArrayField(TEXT("steps"), PlanSteps) || PlanSteps->Num() != 101 ||
            !Manifest->TryGetArrayField(TEXT("actors"), Actors) || Actors->Num() != 25) return false;
        for (const TSharedPtr<FJsonValue>& Value : *PlanSteps)
        {
            const TSharedPtr<FJsonObject> Row = Value->AsObject();
            const TArray<TSharedPtr<FJsonValue>>* SourceValues = nullptr;
            const TArray<TSharedPtr<FJsonValue>>* Buildings = nullptr;
            if (!Row || !Row->TryGetArrayField(TEXT("source_cm"), SourceValues) || SourceValues->Num() != 3 ||
                !Row->TryGetArrayField(TEXT("building_samples"), Buildings)) return false;
            FStep Step;
            Step.Id = Row->GetStringField(TEXT("id"));
            Step.Kind = Row->GetStringField(TEXT("kind"));
            Step.Source = ReadVec(*SourceValues);
            Step.Buildings = *Buildings;
            Steps.Add(MoveTemp(Step));
            for (const TSharedPtr<FJsonValue>& BuildingValue : *Buildings)
            {
                const TSharedPtr<FJsonObject> Sample = BuildingValue->AsObject();
                if (Sample && Sample->GetStringField(TEXT("id")) == TEXT("low_rise_mass"))
                {
                    DynamicSource = Step.Source;
                    DynamicStart = ReadVec(Sample->GetArrayField(TEXT("start_cm")));
                    DynamicEnd = ReadVec(Sample->GetArrayField(TEXT("end_cm")));
                    DynamicExpectedTile = Sample->GetStringField(TEXT("expected_tile"));
                }
            }
        }
        for (const TSharedPtr<FJsonValue>& Value : *Actors)
        {
            const TSharedPtr<FJsonObject> Row = Value->AsObject();
            if (!Row) return false;
            const FString Asset = Row->GetStringField(TEXT("asset_path"));
            const FString Tile = Row->GetStringField(TEXT("tile"));
            if (Asset.IsEmpty() || Tile.IsEmpty() || TileByAsset.Contains(Asset)) return false;
            TileByAsset.Add(Asset, Tile);
        }
        Report->SetNumberField(TEXT("plan_step_count"), Steps.Num());
        return Steps.Num() == 101 && TileByAsset.Num() == 25 && !DynamicExpectedTile.IsEmpty();
    }

    bool Tick(float DeltaSeconds)
    {
        const double Now = FPlatformTime::Seconds();
        if (!World)
        {
            for (const FWorldContext& Context : GEngine->GetWorldContexts())
            {
                UWorld* CandidateWorld = Context.World();
                if (Context.WorldType == EWorldType::Game && CandidateWorld && CandidateWorld->HasBegunPlay() &&
                    CandidateWorld->GetOutermost()->GetName() == WorldPath) { World = CandidateWorld; break; }
            }
            if (!World)
            {
                if (Now - StartedAt > 90.0) Finish(TEXT("FAIL_WORLD_NOT_STARTED"));
                return !Finished;
            }
            if (!InitializeWorld()) { Finish(TEXT("FAIL_WORLD_SETUP")); return false; }
        }
        FrameTimesMs.Add(static_cast<double>(DeltaSeconds) * 1000.0);
        SIZE_T Memory = 0;
        if (FPlatformProcess::GetApplicationMemoryUsage(FPlatformProcess::GetCurrentProcessId(), &Memory))
            PeakProcessMemoryBytes = FMath::Max(PeakProcessMemoryBytes, static_cast<uint64>(Memory));

        if (Index >= Steps.Num()) return TickDynamic(Now);
        const FStep& Step = Steps[Index];
        if (!Moving)
        {
            SourceActor->SetActorLocation(Step.Source);
            Source->EnableStreamingSource();
            StepAt = Now;
            CompleteSince = 0;
            Moving = true;
            UE_LOG(LogTemp, Display, TEXT("XINYI_COMPLEX_MOVE %s mode=%s"), *Step.Id, *Mode);
            return true;
        }
        const bool Complete = IsStreamingComplete(Step.Source);
        CompleteSince = Complete ? (CompleteSince == 0 ? Now : CompleteSince) : 0;
        if (CompleteSince && Now - CompleteSince >= 0.25)
        {
            const double WaitMs = (Now - StepAt) * 1000.0;
            MaxStreamingWaitMs = FMath::Max(MaxStreamingWaitMs, WaitMs);
            Capture(Step, WaitMs);
            ++Index;
            Moving = false;
        }
        else if (Now - StepAt > 90.0)
        {
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
        Spawn.Name = TEXT("XinyiComplexCandidateSource");
        Spawn.ObjectFlags |= RF_Transient;
        SourceActor = World->SpawnActor<AActor>(Steps[0].Source, FRotator::ZeroRotator, Spawn);
        if (!SourceActor) return false;
        USceneComponent* Root = NewObject<USceneComponent>(SourceActor, TEXT("CandidateSourceRoot"), RF_Transient);
        SourceActor->AddInstanceComponent(Root);
        SourceActor->SetRootComponent(Root);
        Root->RegisterComponent();
        Source = NewObject<UWorldPartitionStreamingSourceComponent>(SourceActor, TEXT("CandidateStreamingSource"), RF_Transient);
        Source->TargetState = EStreamingSourceTargetState::Activated;
        SourceActor->AddInstanceComponent(Source);
        Source->RegisterComponent();
        Source->DisableStreamingSource();
        return Subsystem->IsStreamingSourceProviderRegistered(Source);
    }

    bool IsStreamingComplete(const FVector& Position) const
    {
        bool Observed = false;
        for (const FWorldPartitionStreamingSource& RuntimeSource : Partition->GetStreamingSources())
            if (FVector::Distance(RuntimeSource.Location, Position) <= 1.0 &&
                RuntimeSource.TargetState == EStreamingSourceTargetState::Activated) Observed = true;
        return Observed && Source->IsStreamingCompleted() && Subsystem->IsAllStreamingCompleted();
    }

    FString TileForActor(const AActor* Actor) const
    {
        const AStaticMeshActor* StaticActor = Cast<AStaticMeshActor>(Actor);
        UStaticMesh* Mesh = StaticActor && StaticActor->GetStaticMeshComponent() ?
            StaticActor->GetStaticMeshComponent()->GetStaticMesh() : nullptr;
        const FString* Tile = Mesh ? TileByAsset.Find(Mesh->GetPathName()) : nullptr;
        return Tile ? *Tile : FString();
    }

    void ApplyPolicyAndAudit(TSet<FString>& Loaded)
    {
        for (TActorIterator<AStaticMeshActor> It(World); It; ++It)
        {
            UStaticMeshComponent* Component = It->GetStaticMeshComponent();
            UStaticMesh* Mesh = Component ? Component->GetStaticMesh() : nullptr;
            if (!Mesh) continue;
            const FString* Tile = TileByAsset.Find(Mesh->GetPathName());
            if (!Tile) continue;
            Loaded.Add(*Tile);
            UBodySetup* Body = Mesh->GetBodySetup();
            if (!Body) continue;
            if (!OriginalFlagByTile.Contains(*Tile))
                OriginalFlagByTile.Add(*Tile, static_cast<int32>(Body->GetCollisionTraceFlag().GetValue()));
            if (bCandidate && Body->GetCollisionTraceFlag() != CTF_UseComplexAsSimple)
            {
                Body->CollisionTraceFlag = CTF_UseComplexAsSimple;
                Component->RecreatePhysicsState();
                RecreatedComponents.Add(Component->GetPathName());
            }
            if (Audited.Contains(*Tile)) continue;
            Audited.Add(*Tile);
            TSharedRef<FJsonObject> Row = MakeShared<FJsonObject>();
            Row->SetStringField(TEXT("tile"), *Tile);
            Row->SetStringField(TEXT("asset_path"), Mesh->GetPathName());
            Row->SetStringField(TEXT("actor_package"), It->GetPackage()->GetName());
            Row->SetNumberField(TEXT("original_trace_flag_enum"), OriginalFlagByTile[*Tile]);
            Row->SetNumberField(TEXT("effective_trace_flag_enum"), static_cast<int32>(Body->GetCollisionTraceFlag().GetValue()));
            Row->SetBoolField(TEXT("physics_state_recreated"), bCandidate);
            Row->SetNumberField(TEXT("convex_count"), Body->AggGeom.ConvexElems.Num());
            Row->SetNumberField(TEXT("body_resource_bytes"), Body->GetResourceSizeBytes(EResourceSizeMode::Exclusive));
            Policies.Add(MakeShared<FJsonValueObject>(Row));
        }
    }

    TSharedRef<FJsonObject> HitJson(const FHitResult& Hit, bool bHit) const
    {
        TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
        Result->SetBoolField(TEXT("hit"), bHit);
        if (bHit)
        {
            Result->SetStringField(TEXT("actor"), Hit.GetActor() ? Hit.GetActor()->GetPathName() : TEXT(""));
            Result->SetStringField(TEXT("component"), Hit.GetComponent() ? Hit.GetComponent()->GetPathName() : TEXT(""));
            Result->SetStringField(TEXT("building_tile"), TileForActor(Hit.GetActor()));
            Result->SetArrayField(TEXT("location_cm"), Vec(Hit.Location));
            Result->SetNumberField(TEXT("distance_cm"), Hit.Distance);
        }
        return Result;
    }

    TSharedRef<FJsonObject> RunSweep(const FString& ShapeName, const FCollisionShape& Shape,
        const FVector& Start, const FVector& End, const FCollisionQueryParams& Params) const
    {
        FHitResult Hit;
        const uint64 Begin = FPlatformTime::Cycles64();
        const bool bHit = World->SweepSingleByChannel(Hit, Start, End, FQuat::Identity,
            ECC_Visibility, Shape, Params);
        const double QueryUs = FPlatformTime::ToSeconds64(FPlatformTime::Cycles64() - Begin) * 1000000.0;
        TSharedRef<FJsonObject> Result = HitJson(Hit, bHit);
        Result->SetStringField(TEXT("shape"), ShapeName);
        Result->SetBoolField(TEXT("trace_complex"), false);
        Result->SetNumberField(TEXT("query_us"), QueryUs);
        return Result;
    }

    void Capture(const FStep& Step, double WaitMs)
    {
        TSharedRef<FJsonObject> Row = MakeShared<FJsonObject>();
        Row->SetStringField(TEXT("id"), Step.Id);
        Row->SetStringField(TEXT("kind"), Step.Kind);
        Row->SetNumberField(TEXT("streaming_wait_ms"), WaitMs);
        Row->SetBoolField(TEXT("streaming_completed"), true);
        TSet<FString> Loaded;
        ApplyPolicyAndAudit(Loaded);
        Row->SetArrayField(TEXT("loaded_tiles"), StringSet(Loaded));
        TArray<TSharedPtr<FJsonValue>> Results;
        for (const TSharedPtr<FJsonValue>& Value : Step.Buildings)
        {
            const TSharedPtr<FJsonObject> Sample = Value->AsObject();
            const FVector Start = ReadVec(Sample->GetArrayField(TEXT("start_cm")));
            const FVector End = ReadVec(Sample->GetArrayField(TEXT("end_cm")));
            FCollisionQueryParams Params(SCENE_QUERY_STAT(XinyiComplexCandidateLine), false);
            for (TActorIterator<ALandscapeProxy> It(World); It; ++It) Params.AddIgnoredActor(*It);
            FHitResult Hit;
            const uint64 Begin = FPlatformTime::Cycles64();
            const bool bHit = World->LineTraceSingleByChannel(Hit, Start, End, ECC_Visibility, Params);
            const double FirstQueryUs = FPlatformTime::ToSeconds64(FPlatformTime::Cycles64() - Begin) * 1000000.0;
            const uint64 BatchBegin = FPlatformTime::Cycles64();
            for (int32 Repeat = 0; Repeat < QueryRepetitions; ++Repeat)
            {
                FHitResult RepeatedHit;
                World->LineTraceSingleByChannel(RepeatedHit, Start, End, ECC_Visibility, Params);
            }
            const double BatchUs = FPlatformTime::ToSeconds64(FPlatformTime::Cycles64() - BatchBegin) * 1000000.0;
            TSharedRef<FJsonObject> Result = HitJson(Hit, bHit);
            Result->SetStringField(TEXT("id"), Sample->GetStringField(TEXT("id")));
            Result->SetStringField(TEXT("kind"), Sample->GetStringField(TEXT("kind")));
            Result->SetStringField(TEXT("expected_tile"), Sample->GetStringField(TEXT("expected_tile")));
            Result->SetBoolField(TEXT("expect_hit"), Sample->GetBoolField(TEXT("expect_hit")));
            Result->SetBoolField(TEXT("trace_complex"), false);
            Result->SetNumberField(TEXT("first_query_us"), FirstQueryUs);
            Result->SetNumberField(TEXT("benchmark_total_us"), BatchUs);
            Result->SetNumberField(TEXT("benchmark_average_us"), BatchUs / QueryRepetitions);
            TArray<TSharedPtr<FJsonValue>> Sweeps;
            const FString Id = Sample->GetStringField(TEXT("id"));
            if (Id == TEXT("low_rise_wall") || Id == TEXT("gap_between_buildings_+000_+000"))
                Sweeps.Add(MakeShared<FJsonValueObject>(RunSweep(TEXT("sphere_r50_cm"), FCollisionShape::MakeSphere(50.0), Start, End, Params)));
            if (Id == TEXT("high_rise_wall") || Id == TEXT("gap_between_buildings_+000_+000"))
                Sweeps.Add(MakeShared<FJsonValueObject>(RunSweep(TEXT("box_50_50_100_cm"), FCollisionShape::MakeBox(FVector(50.0, 50.0, 100.0)), Start, End, Params)));
            Result->SetArrayField(TEXT("sweeps"), Sweeps);
            Results.Add(MakeShared<FJsonValueObject>(Result));
        }
        Row->SetArrayField(TEXT("building_queries"), Results);
        TArray<TSharedPtr<FJsonValue>> Rows = Report->GetArrayField(TEXT("steps"));
        Rows.Add(MakeShared<FJsonValueObject>(Row));
        Report->SetArrayField(TEXT("steps"), Rows);
        UE_LOG(LogTemp, Display, TEXT("XINYI_COMPLEX_POINT %s mode=%s queries=%d tiles=%d wait_ms=%.0f"),
            *Step.Id, *Mode, Results.Num(), Loaded.Num(), WaitMs);
    }

    bool TickDynamic(double Now)
    {
        if (DynamicPhase == 0)
        {
            SourceActor->SetActorLocation(DynamicSource);
            Source->EnableStreamingSource();
            DynamicAt = Now;
            CompleteSince = 0;
            DynamicPhase = 1;
            return true;
        }
        if (DynamicPhase == 1)
        {
            const bool Complete = IsStreamingComplete(DynamicSource);
            CompleteSince = Complete ? (CompleteSince == 0 ? Now : CompleteSince) : 0;
            if (!(CompleteSince && Now - CompleteSince >= 0.25))
            {
                if (Now - DynamicAt > 90.0) { Finish(TEXT("FAIL_DYNAMIC_STREAM_TIMEOUT")); return false; }
                return true;
            }
            TSet<FString> Loaded;
            ApplyPolicyAndAudit(Loaded);
            FActorSpawnParameters Spawn;
            Spawn.Name = TEXT("XinyiSimulatedCollisionBody");
            Spawn.ObjectFlags |= RF_Transient;
            DynamicActor = World->SpawnActor<AXinyiCollisionDynamicProbe>(DynamicStart, FRotator::ZeroRotator, Spawn);
            if (!DynamicActor || !DynamicActor->CollisionBox) { Finish(TEXT("FAIL_DYNAMIC_SPAWN")); return false; }
            DynamicActor->CollisionBox->SetSimulatePhysics(true);
            DynamicVelocity = (DynamicEnd - DynamicStart).GetSafeNormal() * 2000.0;
            DynamicActor->CollisionBox->SetPhysicsLinearVelocity(DynamicVelocity);
            DynamicAt = Now;
            DynamicPhase = 2;
            return true;
        }
        if (DynamicPhase == 2)
        {
            if (!DynamicActor) { Finish(TEXT("FAIL_DYNAMIC_DESTROYED")); return false; }
            if (!DynamicActor->bObservedBlockingHit && Now - DynamicAt < 4.0) return true;
            TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
            Result->SetStringField(TEXT("object"), TEXT("simulated_box_80cm_CCD_no_gravity"));
            Result->SetBoolField(TEXT("simulate_physics"), DynamicActor->CollisionBox->IsSimulatingPhysics());
            Result->SetArrayField(TEXT("start_cm"), Vec(DynamicStart));
            Result->SetArrayField(TEXT("target_cm"), Vec(DynamicEnd));
            Result->SetArrayField(TEXT("initial_velocity_cm_s"), Vec(DynamicVelocity));
            Result->SetArrayField(TEXT("final_location_cm"), Vec(DynamicActor->GetActorLocation()));
            Result->SetArrayField(TEXT("final_velocity_cm_s"), Vec(DynamicActor->CollisionBox->GetPhysicsLinearVelocity()));
            Result->SetBoolField(TEXT("blocking_hit_observed"), DynamicActor->bObservedBlockingHit);
            Result->SetStringField(TEXT("expected_tile"), DynamicExpectedTile);
            Result->SetStringField(TEXT("hit_tile"), TileForActor(DynamicActor->ObservedHitActor));
            Result->SetStringField(TEXT("hit_actor"), DynamicActor->ObservedHitActor ? DynamicActor->ObservedHitActor->GetPathName() : TEXT(""));
            Result->SetStringField(TEXT("hit_component"), DynamicActor->ObservedHitComponent ? DynamicActor->ObservedHitComponent->GetPathName() : TEXT(""));
            Result->SetArrayField(TEXT("hit_location_cm"), Vec(DynamicActor->ObservedHitLocation));
            Result->SetNumberField(TEXT("elapsed_ms"), (Now - DynamicAt) * 1000.0);
            Report->SetObjectField(TEXT("dynamic_simulation"), Result);
            Finish(TEXT("ENGINE_COMPLEX_CANDIDATE_COMPLETE"));
            return false;
        }
        return true;
    }

    void Finish(const TCHAR* Status)
    {
        if (Finished) return;
        Finished = true;
        if (Report)
        {
            Report->SetStringField(TEXT("status"), Status);
            Report->SetArrayField(TEXT("building_policy"), Policies);
            Report->SetNumberField(TEXT("audited_tile_count"), Audited.Num());
            Report->SetNumberField(TEXT("physics_state_recreated_component_count"), RecreatedComponents.Num());
            Report->SetNumberField(TEXT("peak_process_memory_bytes"), static_cast<double>(PeakProcessMemoryBytes));
            Report->SetNumberField(TEXT("max_streaming_wait_ms"), MaxStreamingWaitMs);
            TSharedRef<FJsonObject> Frames = MakeShared<FJsonObject>();
            Frames->SetNumberField(TEXT("sample_count"), FrameTimesMs.Num());
            Frames->SetNumberField(TEXT("p50_ms"), Percentile(FrameTimesMs, 0.50));
            Frames->SetNumberField(TEXT("p95_ms"), Percentile(FrameTimesMs, 0.95));
            Frames->SetNumberField(TEXT("p99_ms"), Percentile(FrameTimesMs, 0.99));
            Frames->SetNumberField(TEXT("max_ms"), FrameTimesMs.IsEmpty() ? 0.0 : *Algo::MaxElement(FrameTimesMs));
            Report->SetObjectField(TEXT("frame_time"), Frames);
            FString Body;
            FJsonSerializer::Serialize(Report.ToSharedRef(), TJsonWriterFactory<>::Create(&Body));
            if (!OutputPath.IsEmpty() && !IFileManager::Get().FileExists(*OutputPath))
            {
                IFileManager::Get().MakeDirectory(*FPaths::GetPath(OutputPath), true);
                FFileHelper::SaveStringToFile(Body, *OutputPath);
            }
        }
        if (DynamicActor) DynamicActor->Destroy();
        if (SourceActor) SourceActor->Destroy();
        UE_LOG(LogTemp, Display, TEXT("XINYI_COMPLEX_FINISH %s mode=%s"), Status, *Mode);
        FPlatformMisc::RequestExit(false);
    }

    FTSTicker::FDelegateHandle Handle;
    FString PlanPath, ManifestPath, OutputPath, RunId, Mode;
    bool bCandidate = false, Moving = false, Finished = false;
    TArray<FStep> Steps;
    TMap<FString, FString> TileByAsset;
    TMap<FString, int32> OriginalFlagByTile;
    TSet<FString> Audited, RecreatedComponents;
    TArray<TSharedPtr<FJsonValue>> Policies;
    TArray<double> FrameTimesMs;
    TSharedPtr<FJsonObject> Report;
    UWorld* World = nullptr;
    UWorldPartition* Partition = nullptr;
    UWorldPartitionSubsystem* Subsystem = nullptr;
    AActor* SourceActor = nullptr;
    UWorldPartitionStreamingSourceComponent* Source = nullptr;
    AXinyiCollisionDynamicProbe* DynamicActor = nullptr;
    FVector DynamicSource = FVector::ZeroVector, DynamicStart = FVector::ZeroVector;
    FVector DynamicEnd = FVector::ZeroVector, DynamicVelocity = FVector::ZeroVector;
    FString DynamicExpectedTile;
    int32 Index = 0, DynamicPhase = 0;
    double StartedAt = 0, StepAt = 0, CompleteSince = 0, DynamicAt = 0, MaxStreamingWaitMs = 0;
    uint64 PeakProcessMemoryBytes = 0;
};

TUniquePtr<FProbe> Probe;
}

void StartXinyiComplexCandidateProbe()
{
    XinyiComplexCandidate::Probe = MakeUnique<XinyiComplexCandidate::FProbe>();
    XinyiComplexCandidate::Probe->Start();
}
