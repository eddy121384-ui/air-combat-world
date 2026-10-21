#include "FreeFlightPawn.h"

#include "Camera/CameraComponent.h"
#include "Components/SphereComponent.h"
#include "Engine/World.h"
#include "GameFramework/SpringArmComponent.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "ProceduralMeshComponent.h"
#include "UObject/ConstructorHelpers.h"

namespace
{
	constexpr float Gravity = 9.81f;
	constexpr float SpeedResponse = 0.35f;   // 1/s: how fast speed settles on the throttle's cruise speed
	constexpr float BankResponse = 2.5f;     // 1/s: how fast the bank follows the stick (and levels when released)
	constexpr float SeaLevelCm = 100.f;      // the sea plane has no collision: below 1 m TWVD2001 counts as a splash
}

AFreeFlightPawn::AFreeFlightPawn()
{
	PrimaryActorTick.bCanEverTick = true;
	AutoPossessPlayer = EAutoReceiveInput::Disabled;

	Collision = CreateDefaultSubobject<USphereComponent>(TEXT("Collision"));
	Collision->InitSphereRadius(150.f);
	Collision->SetCollisionProfileName(TEXT("Pawn"));
	Collision->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
	RootComponent = Collision;

	PlaneMesh = CreateDefaultSubobject<UProceduralMeshComponent>(TEXT("PaperPlane"));
	PlaneMesh->SetupAttachment(Collision);
	PlaneMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	PlaneMesh->SetCastShadow(true);

	CameraArm = CreateDefaultSubobject<USpringArmComponent>(TEXT("CameraArm"));
	CameraArm->SetupAttachment(Collision);
	CameraArm->TargetArmLength = 1300.f;
	CameraArm->SocketOffset = FVector(0.f, 0.f, 520.f);   // above the wings: the dart reads as a plan shape, not an edge
	CameraArm->bDoCollisionTest = false;   // never pull the camera through the plane on terrain contact
	CameraArm->bEnableCameraLag = true;
	CameraArm->CameraLagSpeed = 10.f;
	CameraArm->bEnableCameraRotationLag = true;
	CameraArm->CameraRotationLagSpeed = 5.f;

	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	Camera->SetupAttachment(CameraArm, USpringArmComponent::SocketName);
	Camera->SetFieldOfView(80.f);
	Camera->SetRelativeRotation(FRotator(-14.f, 0.f, 0.f));
}

void AFreeFlightPawn::BeginPlay()
{
	Super::BeginPlay();
	BuildPaperPlane();
	ResetFlight();
}

void AFreeFlightPawn::BuildPaperPlane()
{
	// Low-poly paper dart, ~6 m long and 5 m span so it reads clearly behind a chase camera. Local frame: X forward, Y right, Z up.
	const FVector Nose(330.f, 0.f, 0.f);
	const FVector TailTop(-270.f, 0.f, 10.f);
	const FVector Keel(-270.f, 0.f, -70.f);
	const FVector WingL(-270.f, -250.f, 40.f);
	const FVector WingR(-270.f, 250.f, 40.f);
	const FVector CreaseL(-270.f, -45.f, 5.f);
	const FVector CreaseR(-270.f, 45.f, 5.f);

	auto AddDoubleSided = [](TArray<FVector>& V, TArray<int32>& I, TArray<FVector>& N, const FVector& A, const FVector& B, const FVector& C)
	{
		const FVector Normal = FVector::CrossProduct(C - A, B - A).GetSafeNormal();
		const int32 Base = V.Num();
		V.Append({A, B, C, A, C, B});
		N.Append({Normal, Normal, Normal, -Normal, -Normal, -Normal});
		I.Append({Base, Base + 1, Base + 2, Base + 3, Base + 4, Base + 5});
	};

	TArray<FVector> WingV, WingN, KeelV, KeelN;
	TArray<int32> WingI, KeelI;
	// Wings: outer panel + inner fold panel per side (the fold gives the dart its shaded crease).
	AddDoubleSided(WingV, WingI, WingN, Nose, WingL, CreaseL);
	AddDoubleSided(WingV, WingI, WingN, Nose, CreaseL, TailTop);
	AddDoubleSided(WingV, WingI, WingN, Nose, TailTop, CreaseR);
	AddDoubleSided(WingV, WingI, WingN, Nose, CreaseR, WingR);
	// Keel: the folded body under the wings, in a contrasting colour.
	AddDoubleSided(KeelV, KeelI, KeelN, Nose, TailTop, Keel);

	const TArray<FVector2D> NoUV;
	const TArray<FLinearColor> NoColor;
	const TArray<FProcMeshTangent> NoTangent;
	TArray<FVector2D> WingUV, KeelUV;
	WingUV.SetNumZeroed(WingV.Num());
	KeelUV.SetNumZeroed(KeelV.Num());
	PlaneMesh->CreateMeshSection_LinearColor(0, WingV, WingI, WingN, WingUV, NoColor, NoTangent, false);
	PlaneMesh->CreateMeshSection_LinearColor(1, KeelV, KeelI, KeelN, KeelUV, NoColor, NoTangent, false);

	if (UMaterialInterface* Base = LoadObject<UMaterialInterface>(nullptr, TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial")))
	{
		UMaterialInstanceDynamic* Paper = UMaterialInstanceDynamic::Create(Base, this);
		Paper->SetVectorParameterValue(TEXT("Color"), FLinearColor(0.85f, 0.85f, 0.82f));
		UMaterialInstanceDynamic* Trim = UMaterialInstanceDynamic::Create(Base, this);
		Trim->SetVectorParameterValue(TEXT("Color"), FLinearColor(0.75f, 0.12f, 0.05f));
		PlaneMesh->SetMaterial(0, Paper);
		PlaneMesh->SetMaterial(1, Trim);
	}
}

void AFreeFlightPawn::ResetFlight()
{
	SetActorLocationAndRotation(StartLocation, FRotator(0.f, StartYawDeg, 0.f), false, nullptr, ETeleportType::TeleportPhysics);
	SpeedMps = StartSpeedMps;
	Throttle = FMath::Clamp((StartSpeedMps - CruiseMinMps) / (CruiseMaxMps - CruiseMinMps), 0.f, 1.f);
	PitchIn = RollIn = YawIn = 0.f;
	bFrozen = false;
	ResetTimer = 0.f;
	if (CameraArm)
	{
		// Snap the lagged camera to the new pose instead of swinging across the map.
		CameraArm->bEnableCameraLag = false;
		CameraArm->bEnableCameraRotationLag = false;
	}
	UpdateAgl();
}

void AFreeFlightPawn::BeginReset(const FString& Why, float Delay)
{
	bFrozen = true;
	ResetTimer = Delay;
	StatusText = Why;
	StatusTimer = Delay;
}

float AFreeFlightPawn::GetHeadingDeg() const
{
	const FVector F = GetActorForwardVector();
	const float Deg = FMath::RadiansToDegrees(FMath::Atan2(F.X, -F.Y));   // 0 = North (-Y), 90 = East (+X)
	return FMath::Fmod(Deg + 360.f, 360.f);
}

void AFreeFlightPawn::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	const float Dt = FMath::Min(DeltaSeconds, 0.1f);   // a hitch must not teleport the plane into a hill

	StatusTimer = FMath::Max(0.f, StatusTimer - Dt);
	if (bFrozen)
	{
		ResetTimer -= Dt;
		if (ResetTimer <= 0.f)
		{
			ResetFlight();
		}
		return;
	}

	if (!CameraArm->bEnableCameraLag)
	{
		CameraArm->bEnableCameraLag = true;
		CameraArm->bEnableCameraRotationLag = true;
	}

	Fly(Dt);
	UpdateAgl();
}

void AFreeFlightPawn::Fly(float Dt)
{
	// Bank angle from the wing axis (robust at any pitch, unlike the Euler roll): + = right wing down, 180 = inverted.
	auto BankOf = [this]() { return FMath::RadiansToDegrees(FMath::Atan2(-GetActorRightVector().Z, GetActorUpVector().Z)); };

	// Stick: pitch rate; left / right commands a BANK ANGLE (released = wings level), so a held thumb never rolls the plane over.
	// Near vertical the bank is undefined and the stick is a plain roll rate.
	float RollDelta = RollIn * RollRateDeg * Dt;
	if (FMath::Abs(GetActorForwardVector().Z) < 0.97f)
	{
		const float BankError = FMath::FindDeltaAngleDegrees(BankOf(), RollIn * MaxBankDeg);
		RollDelta = FMath::Clamp(BankError * BankResponse * Dt, -RollRateDeg * Dt, RollRateDeg * Dt);
	}
	AddActorLocalRotation(FQuat(FRotator(PitchIn * PitchRateDeg * Dt, YawIn * YawRateDeg * Dt, RollDelta)));

	// Coordinated turn: bank turns the plane around the world vertical (g tan(bank) / v), fading out near vertical flight.
	const float Bank = BankOf();
	const float Pitch = FMath::Asin(FMath::Clamp(GetActorForwardVector().Z, -1.f, 1.f));
	const float TurnRate = FMath::Abs(Bank) < 90.f
		? TurnGain * Gravity * FMath::Tan(FMath::DegreesToRadians(FMath::Clamp(Bank, -MaxBankDeg, MaxBankDeg))) / FMath::Max(SpeedMps, MinSpeedMps) * FMath::Cos(Pitch)
		: 0.f;
	AddActorWorldRotation(FQuat(FRotator(0.f, FMath::RadiansToDegrees(TurnRate) * Dt, 0.f)));

	// Speed: settles on the throttle's cruise speed, climbing costs speed and diving gains it.
	const FVector Fwd = GetActorForwardVector();
	const float Cruise = FMath::Lerp(CruiseMinMps, CruiseMaxMps, Throttle);
	SpeedMps += ((Cruise - SpeedMps) * SpeedResponse - Gravity * Fwd.Z) * Dt;
	SpeedMps = FMath::Clamp(SpeedMps, MinSpeedMps, MaxSpeedMps);

	FHitResult Hit;
	AddActorWorldOffset(Fwd * SpeedMps * 100.f * Dt, true, &Hit);
	if (Hit.bBlockingHit && Hit.bStartPenetrating)
	{
		// Started inside some blocking volume (not terrain): move through it rather than crash on spawn.
		AddActorWorldOffset(Fwd * SpeedMps * 100.f * Dt, false);
	}
	else if (Hit.bBlockingHit)
	{
		BeginReset(TEXT("CRASHED - resetting"), 2.0f);
		return;
	}

	const FVector Loc = GetActorLocation();
	if (Loc.Z < SeaLevelCm)
	{
		BeginReset(TEXT("SPLASHED INTO THE SEA - resetting"), 2.0f);
	}
	else if (!PlayArea.IsInside(Loc))
	{
		BeginReset(TEXT("LEFT THE FLIGHT AREA - resetting"), 1.5f);
	}
}

void AFreeFlightPawn::UpdateAgl()
{
	// Height above ground (Landscape) or sea, whichever is closer below the plane.
	const FVector Loc = GetActorLocation();
	FHitResult Hit;
	FCollisionQueryParams Params(SCENE_QUERY_STAT(FreeFlightAgl), false, this);
	const FVector End = Loc - FVector(0.f, 0.f, 500000.f);
	float Agl = Loc.Z / 100.f;
	if (GetWorld()->LineTraceSingleByChannel(Hit, Loc, End, ECC_Visibility, Params))
	{
		Agl = FMath::Min(Agl, Hit.Distance / 100.f);
	}
	AglM = Agl;
}
