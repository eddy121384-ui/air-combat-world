#include "SkyfrontGameUserSettings.h"

#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Engine/Engine.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformTime.h"
#include "Materials/MaterialInterface.h"
#include "Materials/MaterialParameterCollection.h"
#include "Materials/MaterialParameterCollectionInstance.h"
#include "UObject/UObjectIterator.h"

namespace
{
	// Tree distance rows: the mobile twins of MPC_NF_Forest (metres). Row 0 = the PR #55 Mobile Forest Profile, row 3 = the PC forest
	// curve (NearFull 1 km, ThinEnd 3.4 km, gamma 2.2, fade 150 m, shell 1.2-3 km). WpRange = World Partition loading range of the
	// 1 km tree cells (PR #52 default 3.2 km): no point streaming tree cells far beyond the distance at which every tree has dissolved.
	struct FTreeRow { float NearM, EndM, Gamma, FadeM, ShellStartM, ShellEndM, Clump, WpRangeM; };
	const FTreeRow TreeRows[] = {
		{450.f, 1500.f, 1.6f, 100.f, 500.f, 1300.f, 0.5f, 2400.f},
		{700.f, 2200.f, 1.8f, 120.f, 750.f, 1900.f, 0.6f, 2800.f},
		{900.f, 3000.f, 2.0f, 150.f, 1050.f, 2650.f, 0.7f, 3200.f},
		{1000.f, 3400.f, 2.2f, 150.f, 1200.f, 3000.f, 0.7f, 3600.f},
	};
	// Forest density rows: r.DetailMode shows the rank bands 0-0.55 (Low), 0.55-0.78 (Medium), 0.78-1 (High) of nf_mobile_profile.py.
	// RankKeepM must match the visible share so the material's distance thinning spreads exactly the visible trees over its range.
	struct FDensityRow { int32 DetailMode; float Keep, CrownGain, NearCanopy; };
	const FDensityRow DensityRows[] = { {0, 0.55f, 0.10f, 0.6f}, {1, 0.78f, 0.05f, 0.4f}, {2, 1.0f, 0.0f, 0.2f} };
	const float BuildingRowsM[] = {3000.f, 5000.f, 7000.f, 9000.f};
	const float LandscapeLodRows[] = {1.0f, 1.25f, 1.5f, 2.0f};
	const float ResolutionRows[] = {50.f, 62.f, 75.f, 87.f, 100.f};
	struct FShadowRow { float DistanceScale; int32 Cascades, Res; };   // CSM distance of the sun = 3 km x DistanceScale
	const FShadowRow ShadowRows[] = { {0.f, 0, 0}, {0.1333f, 1, 1024}, {0.2f, 2, 1024}, {0.3333f, 2, 2048}, {0.5f, 3, 2048} };
	const int32 FpsRows[] = {30, 60};

	// PR #50 rank bands: rank edges and the HISM end culls baked from the PC curve (nf_trees_band.report.json band_culls_cm).
	const float BandHiRank[] = {0.30f, 0.55f, 0.78f, 1.0f};
	const float BandCullM[] = {1419.77f, 1894.18f, 2639.37f, 3650.0f};
	const int32 BandDetailMode[] = {0, 0, 1, 2};

	//                                   Tree Dens Bld Terr Res Shadow AO Fps
	const int32 PresetRows[4][USkyfrontGameUserSettings::NumRows] = {
		{0, 0, 0, 0, 0, 1, 0, 0},   // Power Saver
		{1, 1, 1, 1, 1, 2, 0, 0},   // Balanced
		{2, 2, 2, 2, 2, 3, 1, 0},   // High
		{3, 2, 3, 3, 3, 4, 1, 0},   // Ultra
	};

	void SetCVar(const TCHAR* Name, float Value)
	{
		if (IConsoleVariable* V = IConsoleManager::Get().FindConsoleVariable(Name))
		{
			V->Set(*FString::SanitizeFloat(Value), ECVF_SetByCode);   // outranks the device profile
		}
	}
	float GetCVar(const TCHAR* Name)
	{
		const IConsoleVariable* V = IConsoleManager::Get().FindConsoleVariable(Name);
		return V ? V->GetFloat() : -1.f;
	}

	bool IsBuildingHism(const UHierarchicalInstancedStaticMeshComponent* C)
	{
		// nf_buildings.py: one HISM of /Engine/BasicShapes/Cube per 1 km town tile, material M_NF_Building.
		const UMaterialInterface* M = C->GetMaterial(0);
		return C->GetStaticMesh() && C->GetStaticMesh()->GetName() == TEXT("Cube") && M && M->GetName().Contains(TEXT("NF_Building"));
	}
}

USkyfrontGameUserSettings* USkyfrontGameUserSettings::Get()
{
	return GEngine ? Cast<USkyfrontGameUserSettings>(GEngine->GetGameUserSettings()) : nullptr;
}

const TCHAR* USkyfrontGameUserSettings::PresetName(int32 P)
{
	static const TCHAR* Names[] = {TEXT("POWER SAVER"), TEXT("BALANCED"), TEXT("HIGH"), TEXT("ULTRA"), TEXT("CUSTOM")};
	return Names[FMath::Clamp(P, 0, 4)];
}

const TCHAR* USkyfrontGameUserSettings::RowName(int32 Row)
{
	static const TCHAR* Names[] = {TEXT("Tree distance"), TEXT("Forest density"), TEXT("Building distance"), TEXT("Terrain detail"),
		TEXT("Render resolution"), TEXT("Shadows"), TEXT("Ambient occlusion"), TEXT("Frame rate cap")};
	return Names[FMath::Clamp(Row, 0, NumRows - 1)];
}

int32 USkyfrontGameUserSettings::RowLevelCount(int32 Row)
{
	static const int32 Counts[] = {UE_ARRAY_COUNT(TreeRows), UE_ARRAY_COUNT(DensityRows), UE_ARRAY_COUNT(BuildingRowsM),
		UE_ARRAY_COUNT(LandscapeLodRows), UE_ARRAY_COUNT(ResolutionRows), UE_ARRAY_COUNT(ShadowRows), 2, UE_ARRAY_COUNT(FpsRows)};
	return Counts[FMath::Clamp(Row, 0, NumRows - 1)];
}

int32 USkyfrontGameUserSettings::GetRow(int32 Row) const
{
	const int32 Values[] = {TreeDistanceLevel, ForestDensityLevel, BuildingDistanceLevel, TerrainDetailLevel, ResolutionLevel, ShadowLevel,
		AmbientOcclusionLevel, FrameRateLevel};
	return FMath::Clamp(Values[FMath::Clamp(Row, 0, NumRows - 1)], 0, RowLevelCount(Row) - 1);
}

FString USkyfrontGameUserSettings::RowValueText(int32 Row) const
{
	const int32 L = GetRow(Row);
	switch (Row)
	{
	case TreeDistance: return FString::Printf(TEXT("%.1f km"), TreeRows[L].EndM / 1000.f);
	case ForestDensity: return FString::Printf(TEXT("%d %%"), FMath::RoundToInt(DensityRows[L].Keep * 100.f));
	case BuildingDistance: return FString::Printf(TEXT("%.0f km"), BuildingRowsM[L] / 1000.f);
	case TerrainDetail: return FString::Printf(TEXT("LOD x%.2f"), LandscapeLodRows[L]);
	case Resolution: return FString::Printf(TEXT("%.0f %%"), ResolutionRows[L]);
	case Shadows: return L == 0 ? FString(TEXT("Off")) : FString::Printf(TEXT("%.0f m"), 3000.f * ShadowRows[L].DistanceScale);
	case AmbientOcclusion: return L ? FString(TEXT("On")) : FString(TEXT("Off"));
	case FrameRate: return FString::Printf(TEXT("%d fps"), FpsRows[L]);
	default: return FString();
	}
}

void USkyfrontGameUserSettings::LoadRowsFromPreset(int32 P)
{
	const int32* R = PresetRows[FMath::Clamp(P, 0, 3)];
	TreeDistanceLevel = R[0]; ForestDensityLevel = R[1]; BuildingDistanceLevel = R[2]; TerrainDetailLevel = R[3];
	ResolutionLevel = R[4]; ShadowLevel = R[5]; AmbientOcclusionLevel = R[6]; FrameRateLevel = R[7];
}

void USkyfrontGameUserSettings::SetPreset(int32 NewPreset)
{
	Preset = FMath::Clamp(NewPreset, 0, 3);
	const int32 KeepFps = FrameRateLevel;   // the frame-rate cap is the player's own choice, presets do not touch it
	LoadRowsFromPreset(Preset);
	FrameRateLevel = KeepFps;
}

void USkyfrontGameUserSettings::StepRow(int32 Row, int32 Delta)
{
	int32* Values[] = {&TreeDistanceLevel, &ForestDensityLevel, &BuildingDistanceLevel, &TerrainDetailLevel, &ResolutionLevel, &ShadowLevel,
		&AmbientOcclusionLevel, &FrameRateLevel};
	int32& V = *Values[FMath::Clamp(Row, 0, NumRows - 1)];
	V = FMath::Clamp(V + Delta, 0, RowLevelCount(Row) - 1);
	if (Row != FrameRate)
	{
		Preset = Custom;
		for (int32 P = 0; P < 4; ++P)   // a row edit that lands exactly on a preset shows that preset again
		{
			bool bSame = true;
			for (int32 R = 0; R < FrameRate; ++R)
			{
				bSame &= GetRow(R) == PresetRows[P][R];
			}
			Preset = bSame ? P : Preset;
		}
	}
}

void USkyfrontGameUserSettings::ResetToDefaults()
{
	Preset = Balanced;
	LoadRowsFromPreset(Balanced);
	bShowDiagnostics = true;
}

void USkyfrontGameUserSettings::SetToDefaults()
{
	Super::SetToDefaults();
	ResetToDefaults();
}

void USkyfrontGameUserSettings::ApplyGraphics(UWorld* World)
{
	const double T0 = FPlatformTime::Seconds();
	const FTreeRow& T = TreeRows[GetRow(TreeDistance)];
	const FDensityRow& D = DensityRows[GetRow(ForestDensity)];
	const FShadowRow& S = ShadowRows[GetRow(Shadows)];

	// Tree band end culls follow the dissolve distance: r.ViewDistanceScale (it multiplies every HISM end cull) = the largest ratio of
	// "distance at which the band's farthest tree has dissolved" to the band's baked cull, over the bands this density shows.
	float Vds = 0.1f;
	for (int32 B = 0; B < 4; ++B)
	{
		if (BandDetailMode[B] <= D.DetailMode)
		{
			const float R = FMath::Min(BandHiRank[B] / D.Keep, 1.f);
			const float Vanish = T.NearM + (T.EndM - T.NearM) * FMath::Pow(R, T.Gamma) + T.FadeM + 100.f;
			Vds = FMath::Max(Vds, Vanish / BandCullM[B]);
		}
	}

	if (D.DetailMode != AppliedDetailMode)
	{
		SetCVar(TEXT("r.DetailMode"), D.DetailMode);   // recreates every render state once (engine scalability callback)
		AppliedDetailMode = D.DetailMode;
	}
	SetCVar(TEXT("r.ViewDistanceScale"), Vds);
	SetCVar(TEXT("foliage.MaxEndCullDistance"), 0.f);   // the PR #55 1.65 km cap also clamped the 9 km town HISMs
	SetCVar(TEXT("r.ScreenPercentage"), ResolutionRows[GetRow(Resolution)]);
	SetCVar(TEXT("r.LandscapeLODDistributionScale"), LandscapeLodRows[GetRow(TerrainDetail)]);
	SetCVar(TEXT("r.LandscapeLOD0DistributionScale"), LandscapeLodRows[GetRow(TerrainDetail)]);
	SetCVar(TEXT("r.ShadowQuality"), S.Cascades > 0 ? 5.f : 0.f);
	if (S.Cascades > 0)
	{
		SetCVar(TEXT("r.Shadow.DistanceScale"), S.DistanceScale);
		SetCVar(TEXT("r.Shadow.CSM.MaxCascades"), S.Cascades);
		SetCVar(TEXT("r.Shadow.MaxCSMResolution"), S.Res);
	}
	SetCVar(TEXT("r.AmbientOcclusionLevels"), GetRow(AmbientOcclusion) ? 1.f : 0.f);
	SetCVar(TEXT("r.Mobile.SSAOHalfResolution"), 2.f);
	const int32 Fps = FpsRows[GetRow(FrameRate)];
	SetCVar(TEXT("t.MaxFPS"), Fps);

	if (World)
	{
		if (GEngine)
		{
			GEngine->Exec(World, *FString::Printf(TEXT("r.SetFramePace %d"), Fps));
			GEngine->Exec(World, *FString::Printf(TEXT("wp.Runtime.OverrideRuntimeSpatialHashLoadingRange -grid=0 -range=%.0f"), T.WpRangeM * 100.f));
		}
		if (UMaterialParameterCollection* Mpc = LoadObject<UMaterialParameterCollection>(nullptr, TEXT("/Game/NorthForest/Materials/MPC_NF_Forest.MPC_NF_Forest")))
		{
			if (UMaterialParameterCollectionInstance* I = World->GetParameterCollectionInstance(Mpc))
			{
				I->SetScalarParameterValue(TEXT("NearFullM"), T.NearM * 100.f);
				I->SetScalarParameterValue(TEXT("ThinEndM"), T.EndM * 100.f);
				I->SetScalarParameterValue(TEXT("ThinGammaM"), T.Gamma);
				I->SetScalarParameterValue(TEXT("FadeWidthM"), T.FadeM * 100.f);
				I->SetScalarParameterValue(TEXT("ShellStartM"), T.ShellStartM * 100.f);
				I->SetScalarParameterValue(TEXT("ShellEndM"), T.ShellEndM * 100.f);
				I->SetScalarParameterValue(TEXT("ClumpGainM"), T.Clump);
				I->SetScalarParameterValue(TEXT("RankKeepM"), D.Keep);
				I->SetScalarParameterValue(TEXT("CrownGainM"), D.CrownGain);
				I->SetScalarParameterValue(TEXT("NearCanopyM"), D.NearCanopy);
			}
		}
		// Town HISMs are not spatially loaded (nf_buildings.py), so they are all present now. Their cull is divided by the view distance
		// scale the trees need, so the town distance stays what the player picked.
		const float BuildingCullCm = BuildingRowsM[GetRow(BuildingDistance)] * 100.f / Vds;
		int32 Count = 0;
		float FirstCull = 0.f;
		for (TObjectIterator<UHierarchicalInstancedStaticMeshComponent> It; It; ++It)
		{
			UHierarchicalInstancedStaticMeshComponent* C = *It;
			if (C->GetWorld() == World && IsBuildingHism(C))
			{
				if (FMath::Abs(C->InstanceEndCullDistance - BuildingCullCm) > 1.f)
				{
					C->SetCullDistances(0, FMath::RoundToInt(BuildingCullCm));
				}
				FirstCull = C->InstanceEndCullDistance;
				++Count;
			}
		}
		Effective.BuildingComponents = Count;
		Effective.BuildingCullM = FirstCull * GetCVar(TEXT("r.ViewDistanceScale")) / 100.f;
	}

	SaveSettings();

	// Read back what the engine now uses (a cvar the device profile pins higher than code would show here).
	Effective.ViewDistanceScale = GetCVar(TEXT("r.ViewDistanceScale"));
	Effective.DetailMode = FMath::RoundToInt(GetCVar(TEXT("r.DetailMode")));
	Effective.MaxEndCullM = GetCVar(TEXT("foliage.MaxEndCullDistance")) / 100.f;
	Effective.TreeEndM = T.EndM;
	Effective.TreeShellStartM = T.ShellStartM;
	Effective.WpLoadingRangeM = T.WpRangeM;
	Effective.ScreenPercentage = GetCVar(TEXT("r.ScreenPercentage"));
	Effective.LandscapeLodScale = GetCVar(TEXT("r.LandscapeLODDistributionScale"));
	Effective.ShadowDistanceM = GetCVar(TEXT("r.ShadowQuality")) > 0.f ? 3000.f * GetCVar(TEXT("r.Shadow.DistanceScale")) : 0.f;
	Effective.Cascades = FMath::RoundToInt(GetCVar(TEXT("r.Shadow.CSM.MaxCascades")));
	Effective.ShadowRes = FMath::RoundToInt(GetCVar(TEXT("r.Shadow.MaxCSMResolution")));
	Effective.AoLevels = FMath::RoundToInt(GetCVar(TEXT("r.AmbientOcclusionLevels")));
	Effective.FpsCap = FMath::RoundToInt(GetCVar(TEXT("t.MaxFPS")));
	Effective.ApplyMs = (FPlatformTime::Seconds() - T0) * 1000.0;
	UE_LOG(LogTemp, Display, TEXT("SKYGFX apply preset=%s tree=%.0fm keep=%.2f dm=%d vds=%.3f bld=%.0fm(%d comps) res=%.0f%% shadow=%.0fm/%d/%d ao=%d fps=%d wp=%.0fm lod=%.2f maxend=%.0f %.1fms"),
		PresetName(Preset), Effective.TreeEndM, D.Keep, Effective.DetailMode, Effective.ViewDistanceScale, Effective.BuildingCullM, Effective.BuildingComponents,
		Effective.ScreenPercentage, Effective.ShadowDistanceM, Effective.Cascades, Effective.ShadowRes, Effective.AoLevels, Effective.FpsCap,
		Effective.WpLoadingRangeM, Effective.LandscapeLodScale, Effective.MaxEndCullM, Effective.ApplyMs);
}
