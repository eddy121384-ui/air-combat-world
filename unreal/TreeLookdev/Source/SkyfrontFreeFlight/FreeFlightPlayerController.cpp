#include "FreeFlightPlayerController.h"

#include "FreeFlightPawn.h"
#include "EngineUtils.h"
#include "HAL/IConsoleManager.h"
#include "Misc/CommandLine.h"
#include "UnrealClient.h"
#include "InputCoreTypes.h"
#include "LevelSequenceActor.h"
#include "LevelSequencePlayer.h"
#include "Misc/App.h"
#include "RHI.h"
#include "SkyfrontGameUserSettings.h"
#include "WorldPartition/WorldPartitionSubsystem.h"
#if WITH_EDITOR
#include "ShaderCompiler.h"
#endif

AFreeFlightPlayerController::AFreeFlightPlayerController()
{
	bShowMouseCursor = false;
	bAutoTest = FParse::Param(FCommandLine::Get(), TEXT("ffautotest"));
	bCrashTest = FParse::Param(FCommandLine::Get(), TEXT("ffcrash"));
	bGfxTest = FParse::Param(FCommandLine::Get(), TEXT("ffgfxtest"));
	bFarLodFly = FParse::Param(FCommandLine::Get(), TEXT("fffarlodfly"));
	bFarLodTest = bFarLodFly || FParse::Param(FCommandLine::Get(), TEXT("fffarlodtest"));
}

void AFreeFlightPlayerController::BeginPlay()
{
	Super::BeginPlay();
	SetInputMode(FInputModeGameOnly());
	ApplyGraphics();   // restore the saved graphics settings (GameUserSettings.ini) on every launch
	if (!bFarLodTest)
	{
		SetFarImpostors(0);   // far-impostor layer off until the FAR button (the command-line A/B sets its own per step)
	}
}

void AFreeFlightPlayerController::ApplyGraphics()
{
	if (USkyfrontGameUserSettings* S = USkyfrontGameUserSettings::Get())
	{
		S->ApplyGraphics(GetWorld());
		LastApplyTime = FPlatformTime::Seconds();
	}
}

void AFreeFlightPlayerController::SetMenuOpen(bool bOpen)
{
	bMenuOpen = bOpen;
	if (AFreeFlightPawn* Plane = Cast<AFreeFlightPawn>(GetPawn()))
	{
		Plane->SetHold(bOpen);   // hold the view still so the change is visible; the world keeps streaming
	}
	StickFinger = ThrottleFinger = INDEX_NONE;
	StickDeflection = FVector2D::ZeroVector;
	RudderTouch = 0.f;
}

bool AFreeFlightPlayerController::HandleMenuPress(const FVector2D& P)
{
	USkyfrontGameUserSettings* S = USkyfrontGameUserSettings::Get();
	if (!S)
	{
		return false;
	}
	for (int32 i = 0; i < 4; ++i)
	{
		if (Menu.Presets[i].IsInside(P)) { S->SetPreset(i); ApplyGraphics(); return true; }
	}
	for (int32 r = 0; r < USkyfrontGameUserSettings::NumRows; ++r)
	{
		if (Menu.RowMinus[r].IsInside(P)) { S->StepRow(r, -1); ApplyGraphics(); return true; }
		if (Menu.RowPlus[r].IsInside(P)) { S->StepRow(r, +1); ApplyGraphics(); return true; }
	}
	if (Menu.Defaults.IsInside(P)) { S->ResetToDefaults(); ApplyGraphics(); return true; }
	if (Menu.Diag.IsInside(P)) { S->SetShowDiagnostics(!S->GetShowDiagnostics()); S->SaveSettings(); return true; }
	if (Menu.FarToggle.IsInside(P)) { SetFarImpostors(IsFarImpostorOn() ? 0 : 2); return true; }
	if (Menu.Bench.IsInside(P)) { StartDeviceBench(); return true; }
	if (Menu.Close.IsInside(P)) { SetMenuOpen(false); return true; }
	return Menu.Panel.IsInside(P);
}

void AFreeFlightPlayerController::KeepCamera()
{
	// The forest map carries the PR #50-#55 perf flight (NF_PerfSequence, auto-play on for packaged perf runs) whose camera cut would
	// take the view away from the plane. Free Flight owns the camera: stop any level sequence and keep the view on the pawn.
	for (TActorIterator<ALevelSequenceActor> It(GetWorld()); It; ++It)
	{
		It->PlaybackSettings.bAutoPlay = false;
		ULevelSequencePlayer* SeqPlayer = It->GetSequencePlayer();
		if (SeqPlayer && SeqPlayer->IsPlaying())
		{
			SeqPlayer->Stop();
		}
	}
	if (GetPawn() && GetViewTarget() != GetPawn())
	{
		SetViewTarget(GetPawn());
	}
}

void AFreeFlightPlayerController::UpdateLayout()
{
	int32 W = 0, H = 0;
	GetViewportSize(W, H);
	const float Wf = FMath::Max(W, 1), Hf = FMath::Max(H, 1);
	const float Top = 0.16f * Hf;   // the strip above is HUD text + buttons
	Layout.StickZone = FBox2D(FVector2D(0.f, Top), FVector2D(0.48f * Wf, Hf));
	Layout.ThrottleZone = FBox2D(FVector2D(0.60f * Wf, Top), FVector2D(Wf, Hf));
	const FVector2D Button(0.24f * Hf, 0.10f * Hf);
	const FVector2D ResetMin(Wf - 0.03f * Hf - Button.X, 0.03f * Hf);
	Layout.ResetButton = FBox2D(ResetMin, ResetMin + Button);
	const FVector2D InvertMin(ResetMin.X - 0.03f * Hf - Button.X, ResetMin.Y);
	Layout.InvertButton = FBox2D(InvertMin, InvertMin + Button);
	const FVector2D GfxMin(InvertMin.X - 0.03f * Hf - Button.X, ResetMin.Y);
	Layout.GfxButton = FBox2D(GfxMin, GfxMin + Button);

	// Menu: a column on the right, 0.98 H wide; touch targets >= 0.068 H (~10 mm on an 11" tablet).
	const float X0 = Wf - 1.0f * Hf, X1 = Wf - 0.02f * Hf;
	Menu.Panel = FBox2D(FVector2D(X0, 0.02f * Hf), FVector2D(X1, 0.98f * Hf));
	const float Pw = (X1 - X0 - 0.05f * Hf) / 4.f;
	for (int32 i = 0; i < 4; ++i)
	{
		const FVector2D Min(X0 + 0.01f * Hf + i * (Pw + 0.01f * Hf), 0.11f * Hf);
		Menu.Presets[i] = FBox2D(Min, Min + FVector2D(Pw, 0.09f * Hf));
	}
	for (int32 r = 0; r < 8; ++r)
	{
		const float Y = 0.235f * Hf + r * 0.077f * Hf;
		Menu.RowLabel[r] = FVector2D(X0 + 0.02f * Hf, Y + 0.02f * Hf);
		Menu.RowMinus[r] = FBox2D(FVector2D(X0 + 0.44f * Hf, Y), FVector2D(X0 + 0.55f * Hf, Y + 0.068f * Hf));
		Menu.RowValue[r] = FVector2D(X0 + 0.705f * Hf, Y + 0.034f * Hf);
		Menu.RowPlus[r] = FBox2D(FVector2D(X0 + 0.86f * Hf, Y), FVector2D(X0 + 0.97f * Hf, Y + 0.068f * Hf));
	}
	// far-LOD research: FAR (impostor layer on / off) and BENCH (on-device A/B) in the title row
	Menu.Bench = FBox2D(FVector2D(X1 - 0.01f * Hf - 0.17f * Hf, 0.028f * Hf), FVector2D(X1 - 0.01f * Hf, 0.095f * Hf));
	Menu.FarToggle = FBox2D(FVector2D(Menu.Bench.Min.X - 0.01f * Hf - 0.21f * Hf, 0.028f * Hf), FVector2D(Menu.Bench.Min.X - 0.01f * Hf, 0.095f * Hf));
	const float Bw = (X1 - X0 - 0.04f * Hf) / 3.f, By = 0.86f * Hf;
	Menu.Defaults = FBox2D(FVector2D(X0 + 0.01f * Hf, By), FVector2D(X0 + 0.01f * Hf + Bw, By + 0.10f * Hf));
	Menu.Diag = FBox2D(FVector2D(X0 + 0.02f * Hf + Bw, By), FVector2D(X0 + 0.02f * Hf + 2.f * Bw, By + 0.10f * Hf));
	Menu.Close = FBox2D(FVector2D(X0 + 0.03f * Hf + 2.f * Bw, By), FVector2D(X0 + 0.03f * Hf + 3.f * Bw, By + 0.10f * Hf));
	Layout.StickRadius = 0.13f * Hf;
	Layout.ThrottleTravel = 0.45f * Hf;
}

void AFreeFlightPlayerController::PollTouches()
{
	AFreeFlightPawn* Plane = Cast<AFreeFlightPawn>(GetPawn());
	for (int32 Finger = 0; Finger < MaxFingers; ++Finger)
	{
		float X = 0.f, Y = 0.f;
		bool bPressed = false;
		if (bAutoTest)
		{
			AutoTestTouch(Finger, X, Y, bPressed);
		}
		else
		{
			GetInputTouchState(static_cast<ETouchIndex::Type>(ETouchIndex::Touch1 + Finger), X, Y, bPressed);
		}
		const FVector2D P(X, Y);

		if (bMenuOpen)
		{
			if (bPressed && !WasPressed[Finger])
			{
				bUsedTouch = true;
				HandleMenuPress(P);   // flight controls are off while the menu is open
			}
		}
		else if (bPressed && !WasPressed[Finger])
		{
			bUsedTouch = true;
			if (Layout.GfxButton.IsInside(P))
			{
				SetMenuOpen(true);
			}
			else if (Layout.ResetButton.IsInside(P))
			{
				if (Plane)
				{
					Plane->ResetFlight();
				}
			}
			else if (Layout.InvertButton.IsInside(P))
			{
				bInvertPitch = !bInvertPitch;
			}
			else if (StickFinger == INDEX_NONE && Layout.StickZone.IsInside(P))
			{
				StickFinger = Finger;
				StickOrigin = P;   // floating stick: centred wherever the thumb lands
				StickDeflection = FVector2D::ZeroVector;
			}
			else if (ThrottleFinger == INDEX_NONE && Layout.ThrottleZone.IsInside(P))
			{
				ThrottleFinger = Finger;
				ThrottleOrigin = P;
				ThrottleAtTouch = Plane ? Plane->GetThrottle() : 0.5f;
			}
		}
		else if (bPressed && Finger == StickFinger)
		{
			FVector2D D = (P - StickOrigin) / Layout.StickRadius;
			if (D.SizeSquared() > 1.f)
			{
				D.Normalize();
			}
			StickDeflection = D;
		}
		else if (bPressed && Finger == ThrottleFinger)
		{
			if (Plane)
			{
				Plane->SetThrottle(ThrottleAtTouch - (P.Y - ThrottleOrigin.Y) / Layout.ThrottleTravel);
			}
			RudderTouch = FMath::Clamp((P.X - ThrottleOrigin.X) / Layout.StickRadius, -1.f, 1.f);
		}
		else if (!bPressed && WasPressed[Finger])
		{
			if (Finger == StickFinger)
			{
				StickFinger = INDEX_NONE;
				StickDeflection = FVector2D::ZeroVector;
			}
			if (Finger == ThrottleFinger)
			{
				ThrottleFinger = INDEX_NONE;
				RudderTouch = 0.f;
			}
		}
		WasPressed[Finger] = bPressed;
	}
}

void AFreeFlightPlayerController::PlayerTick(float DeltaTime)
{
	Super::PlayerTick(DeltaTime);
	TimeSinceStart += DeltaTime;
	CameraCheckTimer -= DeltaTime;
	if (CameraCheckTimer <= 0.f)
	{
		CameraCheckTimer = 0.5f;
		KeepCamera();
	}
	UpdateLayout();
	PollTouches();
	if (bAutoTest)
	{
		AutoTestTick();
	}
	if (bGfxTest)
	{
		GfxTestTick(DeltaTime);
	}
	if (bFarLodTest)
	{
		FarLodTestTick();
	}
	if (WasInputKeyJustPressed(EKeys::G))
	{
		SetMenuOpen(!bMenuOpen);
	}

	AFreeFlightPawn* Plane = Cast<AFreeFlightPawn>(GetPawn());
	if (!Plane || bMenuOpen)
	{
		return;
	}

	// Keyboard / gamepad (desktop testing); touch wins whenever a finger is on the control.
	auto Key = [this](const FKey& K) { return IsInputKeyDown(K) ? 1.f : 0.f; };
	float Pitch = Key(EKeys::S) + Key(EKeys::Down) - Key(EKeys::W) - Key(EKeys::Up) - GetInputAnalogKeyState(EKeys::Gamepad_LeftY);
	float Roll = Key(EKeys::D) + Key(EKeys::Right) - Key(EKeys::A) - Key(EKeys::Left) + GetInputAnalogKeyState(EKeys::Gamepad_LeftX);
	float Yaw = Key(EKeys::E) - Key(EKeys::Q) + GetInputAnalogKeyState(EKeys::Gamepad_RightX);
	if (IsStickActive())
	{
		Pitch = Shape(StickDeflection.Y);   // screen +Y is down = stick back = nose up
		Roll = Shape(StickDeflection.X);
	}
	if (IsThrottleActive())
	{
		Yaw = RudderTouch;
	}
	if (bInvertPitch)
	{
		Pitch = -Pitch;
	}
	Plane->SetControls(FMath::Clamp(Pitch, -1.f, 1.f), FMath::Clamp(Roll, -1.f, 1.f), FMath::Clamp(Yaw, -1.f, 1.f));

	const float ThrottleKeys = Key(EKeys::LeftShift) - Key(EKeys::LeftControl)
		+ GetInputAnalogKeyState(EKeys::Gamepad_RightTriggerAxis) - GetInputAnalogKeyState(EKeys::Gamepad_LeftTriggerAxis);
	if (!IsThrottleActive() && ThrottleKeys != 0.f)
	{
		Plane->SetThrottle(Plane->GetThrottle() + ThrottleKeys * 0.5f * DeltaTime);
	}
	if (WasInputKeyJustPressed(EKeys::R) || WasInputKeyJustPressed(EKeys::Gamepad_Special_Right))
	{
		Plane->ResetFlight();
	}
	if (WasInputKeyJustPressed(EKeys::I))
	{
		bInvertPitch = !bInvertPitch;
	}
}

// -ffautotest: a scripted 34 s flight through the SAME touch handling (synthetic finger samples in viewport pixels instead of
// GetInputTouchState), with a telemetry line per second and HUD screenshots, then quit. Desktop / device smoke test of the controls.
void AFreeFlightPlayerController::AutoTestTouch(int32 Finger, float& X, float& Y, bool& bPressed) const
{
	const float T = TimeSinceStart;
	int32 W = 0, H = 0;
	GetViewportSize(W, H);
	const FVector2D Stick(0.2f * W, 0.7f * H);
	const float R = Layout.StickRadius;
	FVector2D P = FVector2D::ZeroVector;
	bPressed = false;
	if (bCrashTest)
	{
		// -ffcrash: push the stick from t = 2 s and hold it -> dive into the terrain -> CRASHED -> automatic reset 2 s later.
		bPressed = Finger == 0 && T >= 2.f && T < 12.f;
		X = Stick.X;
		Y = Stick.Y - FMath::Min(T - 2.f, 0.5f) * 1.2f * R;
		return;
	}
	if (Finger == 0)
	{
		if (T >= 4.f && T < 7.f) { bPressed = true; P = Stick + FVector2D(0.f, FMath::Min(T - 4.f, 0.5f) * 0.8f * R); }          // pull: climb
		else if (T >= 7.f && T < 9.f) { bPressed = true; P = Stick - FVector2D(0.f, FMath::Min(T - 7.f, 0.5f) * 0.8f * R); }     // push: level off
		else if (T >= 10.f && T < 18.f) { bPressed = true; P = Stick + FVector2D(FMath::Min(T - 10.f, 0.5f) * 1.6f * R, 0.f); } // bank right: turn
		else if (T >= 24.f && T < 27.f) { bPressed = true; P = Stick - FVector2D(0.f, FMath::Min(T - 24.f, 0.5f) * 1.0f * R); } // push: dive
		else if (T >= 30.f && T < 30.3f) { bPressed = true; P = Layout.ResetButton.GetCenter(); }                              // RESET
	}
	else if (Finger == 1 && T >= 20.f && T < 24.f)
	{
		bPressed = true;   // throttle: slide up 0.3 H from where the thumb lands
		P = FVector2D(0.85f * W, 0.8f * H) - FVector2D(0.f, FMath::Min((T - 20.f) / 2.f, 1.f) * 0.3f * H);
	}
	X = P.X;
	Y = P.Y;
}

void AFreeFlightPlayerController::AutoTestTick()
{
	const AFreeFlightPawn* Plane = Cast<AFreeFlightPawn>(GetPawn());
	const int32 Second = FMath::FloorToInt(TimeSinceStart);
	if (!Plane || Second == AutoTestSecond)
	{
		return;
	}
	AutoTestSecond = Second;
	const FVector L = Plane->GetActorLocation();
	const FRotator R = Plane->GetActorRotation();
	extern ENGINE_API float GAverageFPS;
	UE_LOG(LogTemp, Display, TEXT("FFAUTO t=%d x=%.0f y=%.0f alt=%.1f agl=%.1f spd=%.1f hdg=%.1f thr=%.2f pitch=%.1f roll=%.1f stick=%d thrtouch=%d fps=%.1f"),
		Second, L.X, L.Y, Plane->GetAltitudeM(), Plane->GetAglM(), Plane->GetSpeedMps(), Plane->GetHeadingDeg(), Plane->GetThrottle(),
		R.Pitch, R.Roll, IsStickActive() ? 1 : 0, IsThrottleActive() ? 1 : 0, GAverageFPS);
	if (Second == 3 || Second == 7 || Second == 13 || Second == 19 || Second == 23 || Second == 27 || Second == 31)
	{
		FScreenshotRequest::RequestScreenshot(FString::Printf(TEXT("ffauto_t%02d"), Second), true, false);
	}
	if (Second >= 34)
	{
		ConsoleCommand(TEXT("quit"));
	}
}

// -ffgfxtest: same-view graphics comparison.
// Phase A: for each fixed pose the plane holds still, each preset is applied LIVE (as from the menu); once World Partition streaming and
// shader compiles are done, 5 s of frame / GPU time are sampled, then a HUD screenshot is taken and the next preset follows 3 frames LATER
// (so the capture shows the measured preset). One SKYGFXTEST line per (view, preset). Order Power Saver -> Ultra -> Balanced (repeat).
// Phase B: hitch attribution at the first pose from Balanced: each settings row stepped up and back down alone, worst frame over 4 s
// (SKYGFXROW lines). Then quit.
void AFreeFlightPlayerController::GfxTestTick(float DeltaTime)
{
	struct FView { const TCHAR* Name; FVector Loc; FRotator Rot; };
	static const FView Views[] = {
		// 250 m above the Sanzhi north slope looking 8.6 km across the forest bands to Qixingshan (PR #55 dl_layers_north)
		{TEXT("forest_layers"), FVector(420000.0, -3130000.0, 43216.0), FRotator(3.1f, 49.3f, 0.f)},
		// north hills looking 7 km south over Tianmu / Shilin / Beitou (densest town tiles of the map)
		{TEXT("towns_south"), FVector(750000.0, -2300000.0, 90000.0), FRotator(5.0f, 107.1f, 0.f)},
	};
	static const int32 Order[] = {0, 1, 2, 3, 1};
	constexpr int32 NumViews = UE_ARRAY_COUNT(Views), NumPresets = UE_ARRAY_COUNT(Order);
	constexpr int32 NumA = NumViews * NumPresets, NumB = 1 + 2 * USkyfrontGameUserSettings::NumRows;   // B0 = baseline (teleport + Balanced)
	AFreeFlightPawn* Plane = Cast<AFreeFlightPawn>(GetPawn());
	USkyfrontGameUserSettings* S = USkyfrontGameUserSettings::Get();
	if (!Plane || !S)
	{
		return;
	}
	const float FrameMs = FApp::GetDeltaTime() * 1000.f;
	GfxStepTime += FApp::GetDeltaTime();
	bool bAdvance = GfxStep < 0;

	if (GfxShotFrames > 0)
	{
		bAdvance = --GfxShotFrames == 0;   // screenshot taken, now switch
	}
	else if (GfxStep >= NumA)
	{
		// phase B: worst frame of a single-row change
		if (GfxStepTime - FApp::GetDeltaTime() < 4.f)
		{
			GfxWorstAfterApply = FMath::Max(GfxWorstAfterApply, FrameMs);
		}
		else
		{
			const int32 B = GfxStep - NumA - 1, Row = FMath::Max(B, 0) / 2;
			UE_LOG(LogTemp, Display, TEXT("SKYGFXROW row=%s dir=%s value=%s worst_first_4s_ms=%.1f"), B < 0 ? TEXT("baseline") : USkyfrontGameUserSettings::RowName(Row),
				B < 0 ? TEXT("-") : (B % 2 ? TEXT("down") : TEXT("up")), B < 0 ? TEXT("Balanced") : *S->RowValueText(Row), GfxWorstAfterApply);
			if (B < 0)
			{
				FScreenshotRequest::RequestScreenshot(TEXT("skygfx_menu_open"), true, false);   // the baseline step shows the GFX panel
				GfxShotFrames = 3;
			}
			else
			{
				bAdvance = true;
			}
		}
	}
	else if (GfxStep >= 0)
	{
		const float Settle = GfxStep == 0 ? 15.f : 8.f, Measure = 5.f;
		if (GfxReadyAt < 0.f)
		{
			// measure only once World Partition streaming (the loading range changes with the preset) and shader compiles have finished
			const UWorldPartitionSubsystem* Wp = GetWorld()->GetSubsystem<UWorldPartitionSubsystem>();
			bool bReady = !Wp || Wp->IsStreamingCompleted();
#if WITH_EDITOR
			bReady &= !GShaderCompilingManager || GShaderCompilingManager->GetNumRemainingJobs() == 0;
#endif
			if (bReady && GfxStreamDoneAt < 0.f)
			{
				GfxStreamDoneAt = GfxStepTime;
			}
			if ((bReady && GfxStepTime >= Settle) || GfxStepTime >= Settle + 120.f)
			{
				GfxReadyAt = GfxStepTime;
			}
			if (GfxStepTime - FApp::GetDeltaTime() < 3.f)   // frames that STARTED in the first 3 s (a multi-second hitch counts too)
			{
				GfxWorstAfterApply = FMath::Max(GfxWorstAfterApply, FrameMs);
			}
		}
		else if (GfxStepTime < GfxReadyAt + Measure)
		{
			GfxFrameMs.Add(FrameMs);
			GfxGpuMs.Add(FPlatformTime::ToMilliseconds(RHIGetGPUFrameCycles(0)));
		}
		else
		{
			const FView& V = Views[GfxStep / NumPresets];
			GfxFrameMs.Sort();
			GfxGpuMs.Sort();
			auto Pct = [](const TArray<float>& A, float Q) { return A.Num() ? A[FMath::Min(A.Num() - 1, FMath::FloorToInt(A.Num() * Q))] : 0.f; };
			float Sum = 0.f;
			for (float F : GfxFrameMs) { Sum += F; }
			const USkyfrontGameUserSettings::FEffective& E = S->GetEffective();
			UE_LOG(LogTemp, Display, TEXT("SKYGFXTEST view=%s preset=%s frames=%d avg_ms=%.1f p50_ms=%.1f p95_ms=%.1f gpu_p50_ms=%.1f worst_first_3s_ms=%.1f stream_done_s=%.1f tree_end_m=%.0f dm=%d vds=%.3f bld_m=%.0f res=%.0f shadow_m=%.0f cascades=%d ao=%d apply_ms=%.1f"),
				V.Name, USkyfrontGameUserSettings::PresetName(S->GetPreset()), GfxFrameMs.Num(), GfxFrameMs.Num() ? Sum / GfxFrameMs.Num() : 0.f,
				Pct(GfxFrameMs, 0.5f), Pct(GfxFrameMs, 0.95f), Pct(GfxGpuMs, 0.5f), GfxWorstAfterApply, GfxStreamDoneAt, E.TreeEndM, E.DetailMode,
				E.ViewDistanceScale, E.BuildingCullM, E.ScreenPercentage, E.ShadowDistanceM, E.Cascades, E.AoLevels, E.ApplyMs);
			FScreenshotRequest::RequestScreenshot(FString::Printf(TEXT("skygfx_%s_%d_%s"), V.Name, GfxStep % NumPresets,
				USkyfrontGameUserSettings::PresetName(S->GetPreset())).Replace(TEXT(" "), TEXT("_")), true, false);
			GfxShotFrames = 3;
		}
	}
	if (!bAdvance)
	{
		return;
	}

	++GfxStep;
	GfxStepTime = 0.f;
	GfxWorstAfterApply = 0.f;
	GfxReadyAt = GfxStreamDoneAt = -1.f;
	GfxFrameMs.Reset();
	GfxGpuMs.Reset();
	if (GfxStep >= NumA + NumB)
	{
		S->ResetToDefaults();
		S->SaveSettings();
		ConsoleCommand(TEXT("quit"));
		return;
	}
	if (GfxStep < NumA)
	{
		const FView& V = Views[GfxStep / NumPresets];
		Plane->HoldAtPose(V.Loc, V.Rot);
		S->SetPreset(Order[GfxStep % NumPresets]);
	}
	else
	{
		const int32 B = GfxStep - NumA - 1;
		if (B < 0)
		{
			Plane->HoldAtPose(Views[0].Loc, Views[0].Rot);   // baseline: its hitch is not attributed to a row
			S->SetPreset(USkyfrontGameUserSettings::Balanced);
			SetMenuOpen(true);
		}
		else
		{
			if (bMenuOpen)
			{
				SetMenuOpen(false);
				Plane->SetHold(true);
			}
			S->StepRow(B / 2, B % 2 ? -1 : +1);
		}
	}
	ApplyGraphics();
}
