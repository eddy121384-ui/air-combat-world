// Far-LOD research harness (docs/skyfront-far-lod-research-v1.md). Two command-line modes, both on top of the PR #57 graphics presets:
//
// -fffarlodtest  Same-view A/B. For each fixed pose the plane holds still and the configurations below are applied LIVE in the order
//                0..N-1 then N-1..0 (both orders, so a drift or warm-up is not attributed to one config). The far-impostor layer
//                (actors tagged FarImpostor, adapters/unreal/ntwforest/fi_build.py) is toggled in memory - same session, same
//                streaming, same lighting. After World Partition streaming and shader compiles report done, 4 s of frame / GPU time and
//                the RHI draw-call / primitive counters are sampled, then a screenshot WITHOUT UI is taken. One SKYFL line per step.
// -fffarlodfly   High-speed check. For each configuration in -flflycfgs= (default 0,1) the plane is placed at the forest_layers pose,
//                waits for streaming, then is moved 10 m per FRAME (300 m/s at 30 fps; frame-indexed, so every config renders exactly
//                the same camera path) along its heading for -flflyframes= frames (default 360), with a screenshot every frame.
//                One SKYFLFLY line per frame (gpu ms, draws, primitives).
#include "FreeFlightPlayerController.h"

#include "FreeFlightPawn.h"
#include "GameFramework/HUD.h"
#include "EngineUtils.h"
#include "Misc/App.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "RHI.h"
#include "RHIStats.h"
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
		// views_dl.json dl_far_range: backlit far ranges, 10.7 km
		{TEXT("far_range"), FVector(1820000.0, -3260000.0, 40000.0), FRotator(1.6f, 141.84f, 0.f)},
	};
	struct FFlConfig { const TCHAR* Name; int32 Preset; int32 TreeStep; bool bImpostors; };
	const FFlConfig FlConfigs[] = {
		{TEXT("high"), USkyfrontGameUserSettings::High, 0, false},          // PR #57 High (control)
		{TEXT("high_fi"), USkyfrontGameUserSettings::High, 0, true},        // + impostors beyond the preset's 3D hand-over
		{TEXT("high_t22_fi"), USkyfrontGameUserSettings::High, -1, true},   // 3D trees end at 2.2 km, impostors from there
		{TEXT("ultra"), USkyfrontGameUserSettings::Ultra, 0, false},        // PR #57 Ultra (control)
		{TEXT("ultra_fi"), USkyfrontGameUserSettings::Ultra, 0, true},
	};
	constexpr int32 NumFlConfigs = UE_ARRAY_COUNT(FlConfigs);

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

void AFreeFlightPlayerController::SetFarImpostors(bool bOn)
{
	int32 N = 0;
	for (TActorIterator<AActor> It(GetWorld()); It; ++It)
	{
		if (It->ActorHasTag(TEXT("FarImpostor")))
		{
			It->SetActorHiddenInGame(!bOn);
			++N;
		}
	}
	FarImpostorActors = N;
}

void AFreeFlightPlayerController::FarLodTestTick()
{
	AFreeFlightPawn* Plane = Cast<AFreeFlightPawn>(GetPawn());
	USkyfrontGameUserSettings* S = USkyfrontGameUserSettings::Get();
	if (!Plane || !S)
	{
		return;
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
			for (int32 C : ParseList(TEXT("flflycfgs="), {0, 1})) { FlSteps.Add({0, C}); }
			FParse::Value(FCommandLine::Get(), TEXT("flflyframes="), FlFlyFrames);
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
	bool bAdvance = FlStep < 0;
	if (FlShotFrames > 0)
	{
		bAdvance = --FlShotFrames == 0;
	}
	else if (FlStep >= 0)
	{
		const FFlView& V = FlViews[FlSteps[FlStep].X];
		const FFlConfig& C = FlConfigs[FlSteps[FlStep].Y];
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
			// frame-indexed straight flight along the pose heading, 10 m per frame
			const FVector Dir = V.Rot.Vector().GetSafeNormal2D();
			Plane->HoldAtPose(V.Loc + Dir * (1000.0 * FlFlyFrame), V.Rot);
			if (FlFlyFrame > 0)
			{
				UE_LOG(LogTemp, Display, TEXT("SKYFLFLY cfg=%s frame=%d frame_ms=%.1f gpu_ms=%.1f draws=%d prims=%d"), C.Name, FlFlyFrame - 1, FrameMs,
					FPlatformTime::ToMilliseconds(RHIGetGPUFrameCycles(0)), GNumDrawCallsRHI[0], GNumPrimitivesDrawnRHI[0]);
				FScreenshotRequest::RequestScreenshot(FString::Printf(TEXT("fly_%s_%04d"), C.Name, FlFlyFrame - 1), false, false);
			}
			if (++FlFlyFrame > FlFlyFrames + 1)
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
			UE_LOG(LogTemp, Display, TEXT("SKYFL step=%d view=%s cfg=%s frames=%d frame_p50_ms=%.1f gpu_p50_ms=%.1f gpu_min_ms=%.1f gpu_p95_ms=%.1f draws_p50=%.0f prims_p50=%.0f stream_done_s=%.1f used_phys_mb=%.0f tree_end_m=%.0f vds=%.3f fi_actors=%d"),
				FlStep, V.Name, C.Name, FlFrameMs.Num(), Pct(FlFrameMs, 0.5f), Pct(FlGpuMs, 0.5f), Pct(FlGpuMs, 0.f), Pct(FlGpuMs, 0.95f),
				Pct(FlDraws, 0.5f), Pct(FlPrims, 0.5f), FlStreamDoneAt, Mem.UsedPhysical / 1048576.0, S->GetEffective().TreeEndM,
				S->GetEffective().ViewDistanceScale, FarImpostorActors);
			FScreenshotRequest::RequestScreenshot(FString::Printf(TEXT("fl_%s_%02d_%s"), V.Name, FlStep, C.Name), false, false);
			FlShotFrames = 3;
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
	if (FlStep >= FlSteps.Num())
	{
		S->ResetToDefaults();
		S->SetShowDiagnostics(true);
		S->SaveSettings();
		ConsoleCommand(TEXT("quit"));
		return;
	}
	const FFlView& V = FlViews[FlSteps[FlStep].X];
	const FFlConfig& C = FlConfigs[FlSteps[FlStep].Y];
	Plane->HoldAtPose(V.Loc, V.Rot);
	S->SetPreset(C.Preset);
	if (C.TreeStep)
	{
		S->StepRow(USkyfrontGameUserSettings::TreeDistance, C.TreeStep);
	}
	ApplyGraphics();
	SetFarImpostors(C.bImpostors);
}
