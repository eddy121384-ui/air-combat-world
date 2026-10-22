#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerController.h"
#include "FreeFlightPlayerController.generated.h"

class AFreeFlightPawn;

// Tablet controls, polled every frame (no input assets):
//   left side   floating virtual stick: left / right = roll, down / up = pitch (down = nose up, "pilot"; INVERT button flips)
//   right side  throttle: slide up / down (relative to where the finger lands); left / right = rudder, springs back
//   top right   GFX (graphics settings menu), PITCH STD/INV and RESET buttons
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
		FBox2D StickZone, ThrottleZone, ResetButton, InvertButton, GfxButton;
		float StickRadius = 1.f;
		float ThrottleTravel = 1.f;
	};
	const FLayout& GetLayout() const { return Layout; }

	// Graphics settings panel (right side of the screen; the scene stays visible on the left while the plane holds its pose).
	struct FMenuLayout
	{
		FBox2D Panel, Presets[4], RowMinus[8], RowPlus[8], Defaults, Diag, Close;
		FVector2D RowLabel[8], RowValue[8];
	};
	const FMenuLayout& GetMenuLayout() const { return Menu; }
	bool IsMenuOpen() const { return bMenuOpen; }
	double GetLastApplyTime() const { return LastApplyTime; }
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
	void SetMenuOpen(bool bOpen);
	void ApplyGraphics();
	bool HandleMenuPress(const FVector2D& P);
	void GfxTestTick(float DeltaTime);
	void FarLodTestTick();                 // FreeFlightFarLodTest.cpp
	void SetFarImpostors(bool bOn);
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
	FMenuLayout Menu;
	bool bMenuOpen = false;
	double LastApplyTime = -100.0;
	// -ffgfxtest: same-view preset comparison (see GfxTestTick)
	bool bGfxTest = false;
	int32 GfxStep = -1;
	float GfxStepTime = 0.f;
	float GfxWorstAfterApply = 0.f;
	float GfxReadyAt = -1.f;
	int32 GfxShotFrames = 0;
	float GfxStreamDoneAt = -1.f;
	TArray<float> GfxFrameMs, GfxGpuMs;
	// -fffarlodtest / -fffarlodfly: far-LOD research A/B (FreeFlightFarLodTest.cpp)
	bool bFarLodTest = false;
	bool bFarLodFly = false;
	bool bFlProfile = false;
	bool bFlProfiled = false;
	TArray<FIntPoint> FlSteps;             // (view, config)
	int32 FlStep = -1;
	float FlStepTime = 0.f;
	float FlReadyAt = -1.f;
	float FlStreamDoneAt = -1.f;
	int32 FlShotFrames = 0;
	int32 FlFlyFrame = 0;
	int32 FlFlyFrames = 360;
	int32 FarImpostorActors = 0;
	TArray<float> FlFrameMs, FlGpuMs, FlDraws, FlPrims;
};
