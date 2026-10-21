#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"
#include "FreeFlightHUD.generated.h"

// Canvas HUD: speed / altitude / AGL / heading / throttle readout, touch stick + throttle + buttons, status and help text.
UCLASS()
class SKYFRONTFREEFLIGHT_API AFreeFlightHUD : public AHUD
{
	GENERATED_BODY()

public:
	virtual void DrawHUD() override;

private:
	void DrawCircle(const FVector2D& C, float R, const FLinearColor& Color, float Thickness);
	void DrawBox(const FBox2D& B, const FLinearColor& Color, float Thickness);
	void DrawLabel(const FString& Text, const FVector2D& Pos, const FLinearColor& Color, float Scale, bool bCentre = false);
};
