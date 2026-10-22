#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"
#include "FreeFlightPlayerController.h"
#include "FreeFlightHUD.generated.h"

// Canvas HUD: speed / altitude / AGL / heading / throttle readout, touch stick + throttle + buttons, status and help text,
// the graphics settings panel and the on-device diagnostics overlay (FPS, frame / GPU time, mode, effective distances).
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
	void DrawButton(const FBox2D& B, const FString& Text, bool bActive, float Scale, float Thickness);
	void DrawMenu(const class AFreeFlightPlayerController* PC, float S, float T);
	void DrawDiagnostics(const class AFreeFlightPlayerController* PC, float S);
	void UpdateFrameStats();

	// diagnostics: 1 s windows of frame time, GPU time; forest component census every 2 s
	float WinSumMs = 0.f, WinWorstMs = 0.f, WinGpuSumMs = 0.f, WinTime = 0.f;
	int32 WinFrames = 0;
	float AvgMs = 0.f, WorstMs = 0.f, GpuMs = 0.f;
	float WorstSinceApplyMs = 0.f;
	double SeenApplyTime = -1.0;
	float CensusTimer = 0.f;
	int32 TreeComps = 0, TreeCompsShown = 0, BuildingComps = 0;
	int64 TreeInst = 0, TreeInstShown = 0;
	AFreeFlightPlayerController::FFarLodCensus FarCensus;   // far-LOD research overlay line
};
