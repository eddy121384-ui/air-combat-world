#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "FreeFlightGameMode.generated.h"

// Free Flight: spawns the paper plane at its configured start pose (ignores PlayerStarts).
UCLASS()
class SKYFRONTFREEFLIGHT_API AFreeFlightGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	AFreeFlightGameMode();

	virtual void RestartPlayer(AController* NewPlayer) override;
};
