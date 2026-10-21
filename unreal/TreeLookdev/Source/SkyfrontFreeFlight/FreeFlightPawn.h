#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Pawn.h"
#include "FreeFlightPawn.generated.h"

class USphereComponent;
class UProceduralMeshComponent;
class USpringArmComponent;
class UCameraComponent;

// Arcade free-flight paper plane. Kinematic (no physics body): speed follows throttle and is traded against climb / dive, the
// stick commands a pitch rate and a bank angle (released = wings level), and bank produces a coordinated turn. A swept collision sphere detects terrain / sea hits; a crash or leaving the map resets to the start pose.
// World frame of the North Taiwan map: UE X = East, UE -Y = North, UE Z = TWVD2001 height (cm).
UCLASS(Config = Game)
class SKYFRONTFREEFLIGHT_API AFreeFlightPawn : public APawn
{
	GENERATED_BODY()

public:
	AFreeFlightPawn();

	virtual void Tick(float DeltaSeconds) override;

	// Control inputs, written every frame by AFreeFlightPlayerController. Pitch / Roll / Yaw in [-1, 1], positive = nose up /
	// right wing down / nose right. ThrottleTarget in [0, 1].
	void SetControls(float InPitch, float InRoll, float InYaw) { PitchIn = InPitch; RollIn = InRoll; YawIn = InYaw; }
	void SetThrottle(float InThrottle) { Throttle = FMath::Clamp(InThrottle, 0.f, 1.f); }
	float GetThrottle() const { return Throttle; }

	void ResetFlight();

	// Hold: freeze the plane in place (settings menu open, scripted same-view captures); the world keeps ticking and streaming.
	void SetHold(bool bInHold) { bHold = bInHold; }
	bool IsHeld() const { return bHold; }
	void HoldAtPose(const FVector& Location, const FRotator& Rotation);

	float GetSpeedMps() const { return SpeedMps; }
	float GetAltitudeM() const { return GetActorLocation().Z / 100.f; }
	float GetAglM() const { return AglM; }
	float GetHeadingDeg() const;
	float GetStatusTimeLeft() const { return StatusTimer; }
	const FString& GetStatusText() const { return StatusText; }

	// Start pose (configurable in DefaultGame.ini [/Script/SkyfrontFreeFlight.FreeFlightPawn]). Default: over the Sanzhi coast,
	// 800 m, compass heading 144 deg (SE, UE yaw 54) toward Zhuzishan / Datun (EPSG:3826 295600, 2797600 -> UE (-40000, -3760000)).
	UPROPERTY(Config, EditAnywhere, Category = "Free Flight")
	FVector StartLocation = FVector(-40000.0, -3760000.0, 80000.0);

	UPROPERTY(Config, EditAnywhere, Category = "Free Flight")
	float StartYawDeg = 54.f;

	UPROPERTY(Config, EditAnywhere, Category = "Free Flight")
	float StartSpeedMps = 110.f;

	// Playable area (UE cm): the 26.5 km Landscape (X -646000..2000000, Y -4000000..-1354000) plus a margin over sea / land.
	UPROPERTY(Config, EditAnywhere, Category = "Free Flight")
	FBox PlayArea = FBox(FVector(-1146000.0, -4500000.0, -1000.0), FVector(2500000.0, -854000.0, 500000.0));

	UPROPERTY(Config, EditAnywhere, Category = "Free Flight")
	float MinSpeedMps = 35.f;

	UPROPERTY(Config, EditAnywhere, Category = "Free Flight")
	float CruiseMinMps = 50.f;     // steady-state speed at 0 % throttle, level

	UPROPERTY(Config, EditAnywhere, Category = "Free Flight")
	float CruiseMaxMps = 230.f;    // steady-state speed at 100 % throttle, level

	UPROPERTY(Config, EditAnywhere, Category = "Free Flight")
	float MaxSpeedMps = 320.f;

	UPROPERTY(Config, EditAnywhere, Category = "Free Flight")
	float PitchRateDeg = 55.f;

	UPROPERTY(Config, EditAnywhere, Category = "Free Flight")
	float RollRateDeg = 110.f;

	UPROPERTY(Config, EditAnywhere, Category = "Free Flight")
	float YawRateDeg = 18.f;

	UPROPERTY(Config, EditAnywhere, Category = "Free Flight")
	float TurnGain = 1.6f;         // arcade multiplier on the coordinated-turn rate g tan(bank) / v

	UPROPERTY(Config, EditAnywhere, Category = "Free Flight")
	float MaxBankDeg = 75.f;       // full stick deflection = this bank; the coordinated turn uses bank clamped to it

protected:
	virtual void BeginPlay() override;

	UPROPERTY(VisibleAnywhere, Category = "Free Flight")
	TObjectPtr<USphereComponent> Collision;

	UPROPERTY(VisibleAnywhere, Category = "Free Flight")
	TObjectPtr<UProceduralMeshComponent> PlaneMesh;

	UPROPERTY(VisibleAnywhere, Category = "Free Flight")
	TObjectPtr<USpringArmComponent> CameraArm;

	UPROPERTY(VisibleAnywhere, Category = "Free Flight")
	TObjectPtr<UCameraComponent> Camera;

private:
	void BuildPaperPlane();
	void Fly(float Dt);
	void UpdateAgl();
	void BeginReset(const FString& Why, float Delay);

	float PitchIn = 0.f;
	float RollIn = 0.f;
	float YawIn = 0.f;
	float Throttle = 0.5f;
	float SpeedMps = 110.f;
	float AglM = 0.f;

	bool bFrozen = false;          // crashed / out of area, waiting for the reset timer
	bool bHold = false;
	float ResetTimer = 0.f;
	float StatusTimer = 0.f;
	FString StatusText;
};
