#include "FreeFlightGameMode.h"

#include "FreeFlightHUD.h"
#include "FreeFlightPawn.h"
#include "FreeFlightPlayerController.h"

AFreeFlightGameMode::AFreeFlightGameMode()
{
	DefaultPawnClass = AFreeFlightPawn::StaticClass();
	PlayerControllerClass = AFreeFlightPlayerController::StaticClass();
	HUDClass = AFreeFlightHUD::StaticClass();
}

void AFreeFlightGameMode::RestartPlayer(AController* NewPlayer)
{
	const AFreeFlightPawn* Defaults = GetDefault<AFreeFlightPawn>();
	RestartPlayerAtTransform(NewPlayer, FTransform(FRotator(0.f, Defaults->StartYawDeg, 0.f), Defaults->StartLocation));
}
