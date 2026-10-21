#include "FreeFlightPlayerController.h"

#include "FreeFlightPawn.h"
#include "EngineUtils.h"
#include "HAL/IConsoleManager.h"
#include "Misc/CommandLine.h"
#include "UnrealClient.h"
#include "InputCoreTypes.h"
#include "LevelSequenceActor.h"
#include "LevelSequencePlayer.h"

AFreeFlightPlayerController::AFreeFlightPlayerController()
{
	bShowMouseCursor = false;
	bAutoTest = FParse::Param(FCommandLine::Get(), TEXT("ffautotest"));
	bCrashTest = FParse::Param(FCommandLine::Get(), TEXT("ffcrash"));
}

void AFreeFlightPlayerController::BeginPlay()
{
	Super::BeginPlay();
	SetInputMode(FInputModeGameOnly());
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

		if (bPressed && !WasPressed[Finger])
		{
			bUsedTouch = true;
			if (Layout.ResetButton.IsInside(P))
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

	AFreeFlightPawn* Plane = Cast<AFreeFlightPawn>(GetPawn());
	if (!Plane)
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
