#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerController.h"
#include "FreeFlightPlayerController.generated.h"

class AFreeFlightPawn;

// Tablet controls, polled every frame (no input assets):
//   left side   floating virtual stick: left / right = roll, down / up = pitch (down = nose up, "pilot"; INVERT button flips)
//   right side  throttle: slide up / down (relative to where the finger lands); left / right = rudder, springs back
//   top right   RESET and INVERT buttons
// Keyboard / gamepad for desktop testing: W S / A D / Q E, Shift / Ctrl throttle, R reset; left stick, triggers, right stick X.
UCLASS()
class SKYFRONTFREEFLIGHT_API AFreeFlightPlayerController : public APlayerController
{
	GENERATED_BODY()

public:
	AFreeFlightPlayerController();

	virtual void PlayerTick(float DeltaTime) override;
	virtual void CreateTouchInterface() override {}   // our own canvas controls replace the engine's default virtual joysticks

	// Layout + state for the HUD (viewport pixels).
	struct FLayout
	{
		FBox2D StickZone, ThrottleZone, ResetButton, InvertButton;
		float StickRadius = 1.f;
		float ThrottleTravel = 1.f;
	};
	const FLayout& GetLayout() const { return Layout; }
	bool IsStickActive() const { return StickFinger != INDEX_NONE; }
	FVector2D GetStickOrigin() const { return StickOrigin; }
	FVector2D GetStickKnob() const { return StickOrigin + StickDeflection * Layout.StickRadius; }
	bool IsThrottleActive() const { return ThrottleFinger != INDEX_NONE; }
	bool IsPitchInverted() const { return bInvertPitch; }
	float GetTimeSinceStart() const { return TimeSinceStart; }
	bool HasUsedTouch() const { return bUsedTouch; }

protected:
	virtual void BeginPlay() override;

private:
	void UpdateLayout();
	void PollTouches();
	void KeepCamera();
	void AutoTestTouch(int32 Finger, float& X, float& Y, bool& bPressed) const;
	void AutoTestTick();
	static float Shape(float V) { return 0.35f * V + 0.65f * V * V * V; }   // fine control near centre, full rate at the edge

	FLayout Layout;
	static constexpr int32 MaxFingers = 10;
	bool WasPressed[MaxFingers] = {};
	int32 StickFinger = INDEX_NONE;
	int32 ThrottleFinger = INDEX_NONE;
	FVector2D StickOrigin = FVector2D::ZeroVector;
	FVector2D StickDeflection = FVector2D::ZeroVector;   // unit disc; +X right, +Y down (screen)
	FVector2D ThrottleOrigin = FVector2D::ZeroVector;
	float ThrottleAtTouch = 0.f;
	float RudderTouch = 0.f;
	bool bInvertPitch = false;
	bool bUsedTouch = false;
	float TimeSinceStart = 0.f;
	float CameraCheckTimer = 0.f;
	bool bAutoTest = false;
	bool bCrashTest = false;
	int32 AutoTestSecond = -1;
};
