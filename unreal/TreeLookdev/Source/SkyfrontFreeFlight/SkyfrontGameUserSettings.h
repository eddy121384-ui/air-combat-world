#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameUserSettings.h"
#include "SkyfrontGameUserSettings.generated.h"

// Player graphics settings for the North Taiwan forest world (docs/skyfront-graphics-settings-v1.md). Stored with the engine's
// GameUserSettings (Saved/Config/<Platform>/GameUserSettings.ini), restored on the next launch, applied at runtime without a restart.
// One preset sets every row; changing a row afterwards makes the preset "Custom". Each row drives real engine / content state:
//   Tree distance     MPC_NF_Forest mobile twins (NearFullM / ThinEndM / ThinGammaM / FadeWidthM / ShellStartM / ShellEndM / ClumpGainM)
//                     + r.ViewDistanceScale so no visible tree band's HISM end cull falls short of its dissolve distance
//                     + World Partition loading range of the 1 km tree cells
//   Forest density    r.DetailMode 0 / 1 / 2 = the PR #50 rank bands (55 / 78 / 100 % of the trees; all bands are cooked) + RankKeepM
//   Building distance end cull of the town HISMs (set on the components; foliage.MaxEndCullDistance cap removed)
//   Terrain detail    Landscape LOD distribution (r.LandscapeLODDistributionScale / LOD0DistributionScale)
//   Resolution        r.ScreenPercentage of the native back buffer (r.MobileContentScaleFactor 0 on Android)
//   Shadows           CSM distance / cascades (r.Shadow.CSM.MaxCascades) / resolution (or off)
//   Ambient occlusion mobile SSAO (r.Mobile.AmbientOcclusion=1 project-wide; r.AmbientOcclusionLevels switches the pass)
//   Frame rate        t.MaxFPS + r.SetFramePace 30 / 60
UCLASS(Config = GameUserSettings, ConfigDoNotCheckDefaults)
class SKYFRONTFREEFLIGHT_API USkyfrontGameUserSettings : public UGameUserSettings
{
	GENERATED_BODY()

public:
	enum EPreset : int32 { PowerSaver = 0, Balanced = 1, High = 2, Ultra = 3, Custom = 4 };
	enum ERow : int32 { TreeDistance, ForestDensity, BuildingDistance, TerrainDetail, Resolution, Shadows, AmbientOcclusion, FrameRate, NumRows };

	static USkyfrontGameUserSettings* Get();

	static const TCHAR* PresetName(int32 Preset);
	static const TCHAR* RowName(int32 Row);
	static int32 RowLevelCount(int32 Row);
	FString RowValueText(int32 Row) const;

	int32 GetPreset() const { return Preset; }
	int32 GetRow(int32 Row) const;
	void SetPreset(int32 NewPreset);            // sets every row
	void StepRow(int32 Row, int32 Delta);       // -> Custom
	void ResetToDefaults();                     // Balanced
	bool GetShowDiagnostics() const { return bShowDiagnostics; }
	void SetShowDiagnostics(bool bShow) { bShowDiagnostics = bShow; }

	// Effective values after the last apply, read back from the engine where possible (shown by the diagnostics overlay).
	struct FEffective
	{
		float TreeEndM = 0.f, TreeShellStartM = 0.f, ViewDistanceScale = 1.f, BuildingCullM = 0.f, WpLoadingRangeM = 0.f;
		float MaxEndCullM = 0.f, ShadowDistanceM = 0.f, ScreenPercentage = 100.f, LandscapeLodScale = 1.f;
		int32 DetailMode = 0, Cascades = 0, ShadowRes = 0, AoLevels = 0, FpsCap = 0, BuildingComponents = 0;
		float ApplyMs = 0.f;
	};
	// Pushes the settings into the engine for World (cvars, MPC, building HISMs, World Partition). Cheap rows apply immediately;
	// a density change recreates every render state (one hitch, done from the paused menu).
	void ApplyGraphics(UWorld* World);
	const FEffective& GetEffective() const { return Effective; }

	virtual void SetToDefaults() override;

private:
	void LoadRowsFromPreset(int32 P);

	UPROPERTY(Config) int32 Preset = Balanced;
	UPROPERTY(Config) int32 TreeDistanceLevel = 1;
	UPROPERTY(Config) int32 ForestDensityLevel = 1;
	UPROPERTY(Config) int32 BuildingDistanceLevel = 1;
	UPROPERTY(Config) int32 TerrainDetailLevel = 1;
	UPROPERTY(Config) int32 ResolutionLevel = 1;
	UPROPERTY(Config) int32 ShadowLevel = 2;
	UPROPERTY(Config) int32 AmbientOcclusionLevel = 0;
	UPROPERTY(Config) int32 FrameRateLevel = 0;
	UPROPERTY(Config) bool bShowDiagnostics = true;

	FEffective Effective;
	int32 AppliedDetailMode = -1;
};
