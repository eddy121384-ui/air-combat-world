// Far-LOD research harness (docs/skyfront-far-lod-research-v1.md). Command-line modes, on top of the PR #57 graphics presets:
//
// -fffarlodtest  Same-view A/B. For each fixed pose the plane holds still and the configurations below are applied LIVE in the order
//                0..N-1 then N-1..0 (both orders, so drift / warm-up is not attributed to one config). The streamed far-impostor layer
//                (runtime grids FI_B0..FI_B3, one per far-thinning hash band, adapters/unreal/ntwforest/fi_build.py) is switched per config: OFF = both grids'
//                loading range overridden to 1 cm (nothing resident) + hidden; V5 / V6 = default ranges + the MPC_FI_Impostor parameter
//                set of PR #58 (v5) or this pass (v6). After streaming and shader compiles are done, 4 s of frame / GPU time, RHI draws
//                and a census of the resident impostor / 3D-tree instances are sampled, then a screenshot without UI. One SKYFL line
//                per step.
// -fffarlodfly   For each configuration in -flflycfgs= the plane starts at the forest_layers pose, waits for streaming, then flies
//                straight along its heading. Default: frame-locked 10 m per frame (every config renders the same camera path), a
//                screenshot per frame, -flflyframes= frames. With -flflyrealtime: 300 m/s of WALL-CLOCK time for -flflyseconds= (World
//                Partition streaming has to keep up as in the game), census every frame, screenshots every 3rd frame.
//                One SKYFLFLY line per frame.
#include "FreeFlightPlayerController.h"

#include "FreeFlightPawn.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "EngineUtils.h"
#include "GameFramework/HUD.h"
#include "Kismet/KismetMaterialLibrary.h"
#include "Materials/MaterialInterface.h"
#include "Materials/MaterialParameterCollection.h"
#include "Misc/App.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Misc/Parse.h"
#include "RHI.h"
#include "RHIStats.h"
#include "UObject/UObjectIterator.h"
#include "UnrealClient.h"
#include "SkyfrontGameUserSettings.h"
#include "WorldPartition/WorldPartitionSubsystem.h"
#if WITH_EDITOR
#include "ShaderCompiler.h"
#endif

namespace
{
	struct FFlView { const TCHAR* Name; FVector Loc; FRotator Rot; };
	const FFlView FlViews[] = {
		// PR #57 forest_layers: 250 m over the Sanzhi north slope, 8.6 km across the forest bands to Qixingshan
		{TEXT("forest_layers"), FVector(420000.0, -3130000.0, 43216.0), FRotator(3.1f, 49.3f, 0.f)},
		// views_dl.json dl_mid_ridge: 640 m, 7.4 km along the central ridges
		{TEXT("mid_ridge"), FVector(1130000.0, -2220000.0, 63942.0), FRotator(2.0f, -94.17f, 0.f)},
		// views_dl.json agl400_basin_edge: forest edge over the Taipei basin towns
		{TEXT("basin_edge"), FVector(550000.0, -1540000.0, 40264.0), FRotator(-0.5f, -70.35f, 0.f)},
		// views_dl.json dl_far_range: backlit far ranges over the farmland, 10.7 km
		{TEXT("far_range"), FVector(1820000.0, -3260000.0, 40000.0), FRotator(1.6f, 141.84f, 0.f)},
	};
	enum EFi : int32 { FiOff = 0, FiV5 = 1, FiV6 = 2 };
	struct FFlConfig { const TCHAR* Name; int32 Preset; int32 TreeStep; int32 Fi; };
	const FFlConfig FlConfigs[] = {
		{TEXT("high"), USkyfrontGameUserSettings::High, 0, FiOff},          // PR #57 High (control)
		{TEXT("pr58_v5"), USkyfrontGameUserSettings::High, -1, FiV5},       // PR #58 candidate: 3D trees to 2.2 km + impostors (v5 parameters)
		{TEXT("v6"), USkyfrontGameUserSettings::High, -1, FiV6},            // this pass: same + field-tree / ridge fixes, streamed
		{TEXT("ultra"), USkyfrontGameUserSettings::Ultra, 0, FiOff},        // PR #57 Ultra (control)
	};
	constexpr int32 NumFlConfigs = UE_ARRAY_COUNT(FlConfigs);
	// On-device bench (BENCH button): the phone presets with and without the impostor hand-over (v6), no v5 / screenshots.
	const FFlConfig DevConfigs[] = {
		{TEXT("bal"), USkyfrontGameUserSettings::Balanced, 0, FiOff},       // PR #57 Balanced (default preset)
		{TEXT("bal_t15_v6"), USkyfrontGameUserSettings::Balanced, -1, FiV6},   // Balanced, 3D trees to 1.5 km + impostors
		{TEXT("high"), USkyfrontGameUserSettings::High, 0, FiOff},
		{TEXT("high_t22_v6"), USkyfrontGameUserSettings::High, -1, FiV6},   // the PR #58 candidate, v6
		{TEXT("ultra"), USkyfrontGameUserSettings::Ultra, 0, FiOff},
	};
	constexpr int32 NumDevConfigs = UE_ARRAY_COUNT(DevConfigs);

	// MPC_FI_Impostor parameter sets (fi_build.py MPC_V5 / MPC_V6)
	struct FFiParam { const TCHAR* Name; float V5, V6; };
	const FFiParam FiParams[] = {
		{TEXT("S"), 300000.f, 300000.f}, {TEXT("Kmin"), 0.15f, 0.15f}, {TEXT("ScMax"), 1.6f, 1.25f}, {TEXT("End1"), 550000.f, 480000.f},
		{TEXT("End2"), 700000.f, 600000.f}, {TEXT("TerrStart"), 200000.f, 200000.f}, {TEXT("TerrEnd"), 600000.f, 500000.f},
		{TEXT("TerrMax"), 0.6f, 0.75f}, {TEXT("IsoEnd"), 1.0e7f, 280000.f}, {TEXT("IsoScale"), 1.f, 0.f}, {TEXT("IsoGain"), 1.f, 1.3f},
	};
	const TCHAR* FiGrids[] = {TEXT("FI_B0"), TEXT("FI_B1"), TEXT("FI_B2"), TEXT("FI_B3"), TEXT("FI_ISO")};   // fi_build.py v6b band grids

	TArray<int32> ParseList(const TCHAR* Key, const TArray<int32>& Default)
	{
		FString S;
		if (!FParse::Value(FCommandLine::Get(), Key, S, false))   // false: keep the commas
		{
			return Default;
		}
		TArray<FString> Parts;
		S.ParseIntoArray(Parts, TEXT(","));
		TArray<int32> Out;
		for (const FString& P : Parts) { Out.Add(FCString::Atoi(*P)); }
		return Out;
	}
	float Pct(TArray<float> A, float Q)
	{
		A.Sort();
		return A.Num() ? A[FMath::Min(A.Num() - 1, FMath::FloorToInt(A.Num() * Q))] : 0.f;
	}
}

AFreeFlightPlayerController::FFarLodCensus AFreeFlightPlayerController::FarLodCensus() const
{
	// Resident (registered) instances: impostors by layer, and 3D trees (every other non-building HISM). CPU instance-data estimate:
	// 64 B transform + 4 B per custom float, per instance (FInstancedStaticMeshInstanceData + PerInstanceSMCustomData).
	FFarLodCensus C;
	for (TObjectIterator<UInstancedStaticMeshComponent> It; It; ++It)
	{
		const UInstancedStaticMeshComponent* Comp = *It;
		if (Comp->GetWorld() != GetWorld() || !Comp->IsRegistered())
		{
			continue;
		}
		const AActor* Holder = Comp->GetOwner();
		const UMaterialInterface* Mat = Comp->GetMaterial(0);
		const int64 N = Comp->GetInstanceCount();
		const int64 Bytes = N * (64 + 4 * Comp->NumCustomDataFloats);
		if (Holder && Holder->ActorHasTag(TEXT("FarImpostorN")))
		{
			C.NearInst += N; C.FiBytes += Bytes; ++C.FiComps;
		}
		else if (Holder && Holder->ActorHasTag(TEXT("FarImpostor")))
		{
			C.FarInst += N; C.FiBytes += Bytes; ++C.FiComps;
		}
		else if (Comp->IsA<UHierarchicalInstancedStaticMeshComponent>() && !(Mat && Mat->GetName().Contains(TEXT("NF_Building"))))
		{
			C.TreeInst += N; C.TreeBytes += Bytes;
		}
	}
	return C;
}

void AFreeFlightPlayerController::SetFarImpostors(int32 Mode)
{
	FlFiMode = Mode;
	for (const TCHAR* Grid : FiGrids)   // OFF: nothing of the layer is resident; ON: the grids' own loading ranges
	{
		ConsoleCommand(FString::Printf(TEXT("wp.Runtime.OverrideRuntimeLoadingRange -grid=%s -range=%d"), Grid, Mode == FiOff ? 1 : -1));
	}
	if (Mode != FiOff)
	{
		if (UMaterialParameterCollection* Mpc = LoadObject<UMaterialParameterCollection>(nullptr, TEXT("/Game/FarLOD/Materials/MPC_FI_Impostor.MPC_FI_Impostor")))
		{
			for (const FFiParam& P : FiParams)
			{
				UKismetMaterialLibrary::SetScalarParameterValue(this, Mpc, P.Name, Mode == FiV5 ? P.V5 : P.V6);
			}
		}
	}
	ApplyFarImpostorVisibility();
}

void AFreeFlightPlayerController::ApplyFarImpostorVisibility()
{
	int32 N = 0;
	for (TActorIterator<AActor> It(GetWorld()); It; ++It)
	{
		if (It->ActorHasTag(TEXT("FarImpostor")))
		{
			if (It->IsHidden() != (FlFiMode == FiOff))
			{
				It->SetActorHiddenInGame(FlFiMode == FiOff);
			}
			++N;
		}
	}
	FarImpostorActors = N;
}

FString AFreeFlightPlayerController::GetBenchStatus() const
{
	if (!IsBenchRunning() || FlStep < 0 || FlStep >= FlSteps.Num())
	{
		return FString();
	}
	return FString::Printf(TEXT("FAR-LOD BENCH %d/%d  %s  %s  (hands off, ~%d min left)"), FlStep + 1, FlSteps.Num(), FlViews[FlSteps[FlStep].X].Name,
		DevConfigs[FlSteps[FlStep].Y].Name, FMath::Max(1, (FlSteps.Num() - FlStep) * 12 / 60));
}

void AFreeFlightPlayerController::StartDeviceBench()
{
	if (USkyfrontGameUserSettings* S = USkyfrontGameUserSettings::Get())
	{
		S->SaveSettings();   // restored when the bench ends
	}
	FlUserFiMode = FlFiMode;
	bFarLodTest = bFlDeviceBench = true;
	bShowBenchResults = false;
	FlSteps.Reset();
	FlStep = -1;
	FlStepTime = 0.f;
	FlShotFrames = 0;
	FlBenchGpu.Reset();
	FlBenchFrame.Reset();
	FlBenchMem.Reset();
	SetMenuOpen(false);
}

void AFreeFlightPlayerController::FinishDeviceBench()
{
	FlBenchLines.Reset();
	FlBenchLines.Add(FString::Printf(TEXT("FAR-LOD BENCH  GPU ms p50 (mean of 2 visits, both orders)   %s"), GDynamicRHI ? GDynamicRHI->GetName() : TEXT("?")));
	FString Head = TEXT("view          ");
	for (const FFlConfig& C : DevConfigs) { Head += FString::Printf(TEXT("%13s"), C.Name); }
	FlBenchLines.Add(Head);
	for (const FFlView& V : FlViews)
	{
		FString Row = FString::Printf(TEXT("%-14s"), V.Name);
		for (const FFlConfig& C : DevConfigs)
		{
			const TArray<float>* G = FlBenchGpu.Find(FString::Printf(TEXT("%s|%s"), V.Name, C.Name));
			float Sum = 0.f;
			for (float X : G ? *G : TArray<float>()) { Sum += X; }
			Row += G && G->Num() ? FString::Printf(TEXT("%13.1f"), Sum / G->Num()) : FString::Printf(TEXT("%13s"), TEXT("-"));
		}
		FlBenchLines.Add(Row);
	}
	FlBenchLines.Add(TEXT("resident at forest_layers (MB, CPU instance data):"));
	for (const FFlConfig& C : DevConfigs)
	{
		if (const FString* M = FlBenchMem.Find(C.Name)) { FlBenchLines.Add(FString::Printf(TEXT("  %-12s %s"), C.Name, **M)); }
	}
	const FString Text = FString::Join(FlBenchLines, TEXT("\n"));
	for (const FString& L : FlBenchLines) { UE_LOG(LogTemp, Display, TEXT("SKYFLBENCH %s"), *L); }
	FFileHelper::SaveStringToFile(Text, *FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("FarLodBench.txt")));
	bFarLodTest = bFlDeviceBench = false;
	bShowBenchResults = true;
	if (USkyfrontGameUserSettings* S = USkyfrontGameUserSettings::Get())
	{
		S->LoadSettings(true);
		S->SetShowDiagnostics(true);
	}
	ApplyGraphics();
	SetFarImpostors(FlUserFiMode);
	if (AFreeFlightPawn* Plane = Cast<AFreeFlightPawn>(GetPawn()))
	{
		Plane->SetHold(false);
	}
}

void AFreeFlightPlayerController::FarLodTestTick()
{
	AFreeFlightPawn* Plane = Cast<AFreeFlightPawn>(GetPawn());
	USkyfrontGameUserSettings* S = USkyfrontGameUserSettings::Get();
	if (!Plane || !S)
	{
		return;
	}
	if (FlSteps.Num() == 0 && bFlDeviceBench)
	{
		for (int32 V = 0; V < UE_ARRAY_COUNT(FlViews); ++V)
		{
			for (int32 C = 0; C < NumDevConfigs; ++C) { FlSteps.Add({V, C}); }
			for (int32 C = NumDevConfigs - 1; C >= 0; --C) { FlSteps.Add({V, C}); }
		}
	}
	if (FlSteps.Num() == 0)
	{
		S->SetShowDiagnostics(false);
		if (MyHUD)
		{
			MyHUD->bShowHUD = false;   // clean A/B frames (the HUD is drawn on the canvas, not by Slate)
		}
		bFlProfile = FParse::Param(FCommandLine::Get(), TEXT("flprofile"));
		if (bFarLodFly)
		{
			for (int32 C : ParseList(TEXT("flflycfgs="), {0, 2})) { FlSteps.Add({0, C}); }
			FParse::Value(FCommandLine::Get(), TEXT("flflyframes="), FlFlyFrames);
			bFlRealtime = FParse::Param(FCommandLine::Get(), TEXT("flflyrealtime"));
			FParse::Value(FCommandLine::Get(), TEXT("flflyseconds="), FlFlySeconds);
		}
		else
		{
			for (int32 V : ParseList(TEXT("flviews="), {0, 1, 2, 3}))
			{
				for (int32 C = 0; C < NumFlConfigs; ++C) { FlSteps.Add({V, C}); }
				for (int32 C = NumFlConfigs - 1; C >= 0; --C) { FlSteps.Add({V, C}); }
			}
		}
	}
	const float FrameMs = FApp::GetDeltaTime() * 1000.f;
	FlStepTime += FApp::GetDeltaTime();
	FlVisTimer -= FApp::GetDeltaTime();
	if (FlVisTimer <= 0.f)
	{
		FlVisTimer = 0.25f;
		ApplyFarImpostorVisibility();   // cells streamed in since the last switch follow the current mode
	}
	bool bAdvance = FlStep < 0;
	if (FlShotFrames > 0)
	{
		bAdvance = --FlShotFrames == 0;
	}
	else if (FlStep >= 0)
	{
		const FFlView& V = FlViews[FlSteps[FlStep].X];
		const FFlConfig& C = bFlDeviceBench ? DevConfigs[FlSteps[FlStep].Y] : FlConfigs[FlSteps[FlStep].Y];
		if (FlReadyAt < 0.f)
		{
			const UWorldPartitionSubsystem* Wp = GetWorld()->GetSubsystem<UWorldPartitionSubsystem>();
			bool bReady = !Wp || Wp->IsStreamingCompleted();
#if WITH_EDITOR
			bReady &= !GShaderCompilingManager || GShaderCompilingManager->GetNumRemainingJobs() == 0;
#endif
			if (bReady && FlStreamDoneAt < 0.f)
			{
				FlStreamDoneAt = FlStepTime;
			}
			const float Settle = FlStep == 0 ? 20.f : (bFarLodFly ? 15.f : 6.f);
			if ((bReady && FlStepTime >= Settle) || FlStepTime >= Settle + 120.f)
			{
				FlReadyAt = FlStepTime;
				FlFlyFrame = 0;
			}
		}
		else if (bFarLodFly)
		{
			const FVector Dir = V.Rot.Vector().GetSafeNormal2D();
			const float FlyT = FlStepTime - FlReadyAt;
			const double Along = bFlRealtime ? 30000.0 * FlyT : 1000.0 * FlFlyFrame;   // 300 m/s wall clock, or 10 m per frame
			Plane->HoldAtPose(V.Loc + Dir * Along, V.Rot);
			if (FlFlyFrame > 0)
			{
				const FFarLodCensus Cen = FarLodCensus();
				const UWorldPartitionSubsystem* Wp = GetWorld()->GetSubsystem<UWorldPartitionSubsystem>();
				UE_LOG(LogTemp, Display, TEXT("SKYFLFLY cfg=%s frame=%d t=%.2f along_m=%.0f frame_ms=%.1f gpu_ms=%.1f draws=%d near_inst=%lld far_inst=%lld fi_mb=%.1f tree_inst=%lld stream_done=%d"),
					C.Name, FlFlyFrame - 1, FlyT, Along / 100.0, FrameMs, FPlatformTime::ToMilliseconds(RHIGetGPUFrameCycles(0)), GNumDrawCallsRHI[0],
					Cen.NearInst, Cen.FarInst, Cen.FiBytes / 1048576.0, Cen.TreeInst, Wp && Wp->IsStreamingCompleted() ? 1 : 0);
				if (!bFlRealtime || (FlFlyFrame - 1) % 3 == 0)
				{
					FScreenshotRequest::RequestScreenshot(FString::Printf(TEXT("fly_%s_%04d"), C.Name, FlFlyFrame - 1), false, false);
				}
			}
			++FlFlyFrame;
			if (bFlRealtime ? FlyT > FlFlySeconds : FlFlyFrame > FlFlyFrames + 1)
			{
				bAdvance = true;
			}
		}
		else if (FlStepTime < FlReadyAt + 4.f)
		{
			if (bFlProfile && !bFlProfiled && FlStepTime >= FlReadyAt + 2.f)
			{
				bFlProfiled = true;
				UE_LOG(LogTemp, Display, TEXT("SKYFLPROFILE step=%d view=%s cfg=%s"), FlStep, V.Name, C.Name);
				ConsoleCommand(TEXT("ProfileGPU"));   // one-frame pass breakdown into the log, mid-measurement (not on the screenshot frame)
			}
			FlFrameMs.Add(FrameMs);
			FlGpuMs.Add(FPlatformTime::ToMilliseconds(RHIGetGPUFrameCycles(0)));
			FlDraws.Add(GNumDrawCallsRHI[0]);
			FlPrims.Add(GNumPrimitivesDrawnRHI[0]);
		}
		else
		{
			const FPlatformMemoryStats Mem = FPlatformMemory::GetStats();
			const FFarLodCensus Cen = FarLodCensus();
			UE_LOG(LogTemp, Display, TEXT("SKYFL step=%d view=%s cfg=%s frames=%d frame_p50_ms=%.1f gpu_p50_ms=%.1f gpu_min_ms=%.1f gpu_p95_ms=%.1f draws_p50=%.0f prims_p50=%.0f stream_done_s=%.1f used_phys_mb=%.0f tree_end_m=%.0f vds=%.3f fi_actors=%d fi_comps=%d near_inst=%lld far_inst=%lld fi_mb=%.1f tree_inst=%lld tree_mb=%.1f"),
				FlStep, V.Name, C.Name, FlFrameMs.Num(), Pct(FlFrameMs, 0.5f), Pct(FlGpuMs, 0.5f), Pct(FlGpuMs, 0.f), Pct(FlGpuMs, 0.95f),
				Pct(FlDraws, 0.5f), Pct(FlPrims, 0.5f), FlStreamDoneAt, Mem.UsedPhysical / 1048576.0, S->GetEffective().TreeEndM,
				S->GetEffective().ViewDistanceScale, FarImpostorActors, Cen.FiComps, Cen.NearInst, Cen.FarInst, Cen.FiBytes / 1048576.0,
				Cen.TreeInst, Cen.TreeBytes / 1048576.0);
			if (bFlDeviceBench)
			{
				FlBenchGpu.FindOrAdd(FString::Printf(TEXT("%s|%s"), V.Name, C.Name)).Add(Pct(FlGpuMs, 0.5f));
				FlBenchFrame.FindOrAdd(FString::Printf(TEXT("%s|%s"), V.Name, C.Name)).Add(Pct(FlFrameMs, 0.5f));
				if (FlSteps[FlStep].X == 0)
				{
					FlBenchMem.Add(C.Name, FString::Printf(TEXT("impostors %.0f MB (%lld k)  3D trees %.0f MB (%lld k)  process %.0f MB"),
						Cen.FiBytes / 1048576.0, (Cen.NearInst + Cen.FarInst) / 1000, Cen.TreeBytes / 1048576.0, Cen.TreeInst / 1000, Mem.UsedPhysical / 1048576.0));
				}
				FlShotFrames = 1;
			}
			else
			{
				FScreenshotRequest::RequestScreenshot(FString::Printf(TEXT("fl_%s_%02d_%s"), V.Name, FlStep, C.Name), false, false);
				FlShotFrames = 3;
			}
		}
	}
	if (!bAdvance)
	{
		return;
	}
	++FlStep;
	FlStepTime = 0.f;
	FlReadyAt = FlStreamDoneAt = -1.f;
	bFlProfiled = false;
	FlFrameMs.Reset();
	FlGpuMs.Reset();
	FlDraws.Reset();
	FlPrims.Reset();
	if (FlStep >= FlSteps.Num() && bFlDeviceBench)
	{
		FinishDeviceBench();
		return;
	}
	if (FlStep >= FlSteps.Num())
	{
		S->ResetToDefaults();
		S->SetShowDiagnostics(true);
		S->SaveSettings();
		ConsoleCommand(TEXT("quit"));
		return;
	}
	const FFlView& V = FlViews[FlSteps[FlStep].X];
	const FFlConfig& C = bFlDeviceBench ? DevConfigs[FlSteps[FlStep].Y] : FlConfigs[FlSteps[FlStep].Y];
	Plane->HoldAtPose(V.Loc, V.Rot);
	S->SetPreset(C.Preset);
	if (C.TreeStep)
	{
		S->StepRow(USkyfrontGameUserSettings::TreeDistance, C.TreeStep);
	}
	ApplyGraphics();
	SetFarImpostors(C.Fi);
}
