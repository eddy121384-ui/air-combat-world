#include "FreeFlightHUD.h"

#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Engine/Font.h"
#include "FreeFlightPawn.h"
#include "FreeFlightPlayerController.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "DeviceProfiles/DeviceProfileManager.h"
#include "DynamicRHI.h"
#include "Engine/StaticMesh.h"
#include "HAL/IConsoleManager.h"
#include "Materials/MaterialInterface.h"
#include "Misc/App.h"
#include "RHI.h"
#include "Scalability.h"
#include "SkyfrontGameUserSettings.h"
#include "UObject/UObjectIterator.h"

namespace
{
	const FLinearColor HudGreen(0.55f, 1.f, 0.6f, 0.95f);
	const FLinearColor HudDim(0.75f, 0.85f, 0.8f, 0.5f);
	const FLinearColor HudWarn(1.f, 0.3f, 0.2f, 1.f);

	const TCHAR* Cardinal(float Deg)
	{
		static const TCHAR* Names[] = {TEXT("N"), TEXT("NE"), TEXT("E"), TEXT("SE"), TEXT("S"), TEXT("SW"), TEXT("W"), TEXT("NW")};
		return Names[FMath::RoundToInt(Deg / 45.f) % 8];
	}
}

void AFreeFlightHUD::DrawCircle(const FVector2D& C, float R, const FLinearColor& Color, float Thickness)
{
	constexpr int32 Segments = 40;
	for (int32 i = 0; i < Segments; ++i)
	{
		const float A0 = 2.f * PI * i / Segments, A1 = 2.f * PI * (i + 1) / Segments;
		DrawLine(C.X + R * FMath::Cos(A0), C.Y + R * FMath::Sin(A0), C.X + R * FMath::Cos(A1), C.Y + R * FMath::Sin(A1), Color, Thickness);
	}
}

void AFreeFlightHUD::DrawBox(const FBox2D& B, const FLinearColor& Color, float Thickness)
{
	DrawLine(B.Min.X, B.Min.Y, B.Max.X, B.Min.Y, Color, Thickness);
	DrawLine(B.Max.X, B.Min.Y, B.Max.X, B.Max.Y, Color, Thickness);
	DrawLine(B.Max.X, B.Max.Y, B.Min.X, B.Max.Y, Color, Thickness);
	DrawLine(B.Min.X, B.Max.Y, B.Min.X, B.Min.Y, Color, Thickness);
}

void AFreeFlightHUD::DrawLabel(const FString& Text, const FVector2D& Pos, const FLinearColor& Color, float Scale, bool bCentre)
{
	UFont* Font = GEngine->GetLargeFont();
	FVector2D P = Pos;
	if (bCentre)
	{
		float TW = 0.f, TH = 0.f;
		GetTextSize(Text, TW, TH, Font, Scale);
		P -= FVector2D(TW, TH) * 0.5f;
	}
	DrawText(Text, FLinearColor(0.f, 0.f, 0.f, 0.6f), P.X + 2.f, P.Y + 2.f, Font, Scale);   // drop shadow over bright sky
	DrawText(Text, Color, P.X, P.Y, Font, Scale);
}

void AFreeFlightHUD::DrawHUD()
{
	Super::DrawHUD();
	const AFreeFlightPlayerController* PC = Cast<AFreeFlightPlayerController>(PlayerOwner);
	const AFreeFlightPawn* Plane = PC ? Cast<AFreeFlightPawn>(PC->GetPawn()) : nullptr;
	if (!Canvas || !PC || !Plane)
	{
		return;
	}

	const float H = Canvas->SizeY, W = Canvas->SizeX;
	const float S = H / 1080.f;          // text scale: the large engine font is ~24 px at 1080p
	const float T = FMath::Max(2.f, 3.f * S);
	const auto& L = PC->GetLayout();

	UpdateFrameStats();
	const USkyfrontGameUserSettings* Gfx = USkyfrontGameUserSettings::Get();
	if (Gfx && Gfx->GetShowDiagnostics())
	{
		DrawDiagnostics(PC, S);
	}
	if (PC->IsMenuOpen())
	{
		DrawMenu(PC, S, T);
		return;   // flight widgets hidden while the panel is open (the plane holds still)
	}

	// Flight readout (top left).
	const float Heading = Plane->GetHeadingDeg();
	const float Agl = Plane->GetAglM();
	const FVector2D TL(0.03f * H, 0.03f * H);
	DrawLabel(FString::Printf(TEXT("SPD %4d km/h"), FMath::RoundToInt(Plane->GetSpeedMps() * 3.6f)), TL, HudGreen, 1.5f * S);
	DrawLabel(FString::Printf(TEXT("ALT %5d m"), FMath::RoundToInt(Plane->GetAltitudeM())), TL + FVector2D(0.f, 0.05f * H), HudGreen, 1.5f * S);
	DrawLabel(FString::Printf(TEXT("AGL %5d m"), FMath::RoundToInt(Agl)), TL + FVector2D(0.f, 0.10f * H), Agl < 80.f ? HudWarn : HudGreen, 1.5f * S);
	DrawLabel(FString::Printf(TEXT("HDG %03d %s"), FMath::RoundToInt(Heading) % 360, Cardinal(Heading)), FVector2D(0.5f * W, 0.04f * H), HudGreen, 1.7f * S, true);

	// Centre marker.
	DrawLine(0.5f * W - 0.02f * H, 0.5f * H, 0.5f * W - 0.006f * H, 0.5f * H, HudGreen, T);
	DrawLine(0.5f * W + 0.006f * H, 0.5f * H, 0.5f * W + 0.02f * H, 0.5f * H, HudGreen, T);

	if (Agl < 80.f && Plane->GetStatusTimeLeft() <= 0.f)
	{
		DrawLabel(TEXT("PULL UP"), FVector2D(0.5f * W, 0.36f * H), HudWarn, 2.2f * S, true);
	}

	// Throttle bar (right edge) + percentage.
	const float Thr = Plane->GetThrottle();
	const FBox2D Bar(FVector2D(W - 0.07f * H, 0.40f * H), FVector2D(W - 0.035f * H, 0.92f * H));
	DrawRect(FLinearColor(0.f, 0.f, 0.f, 0.3f), Bar.Min.X, Bar.Min.Y, Bar.GetSize().X, Bar.GetSize().Y);
	const float FillH = Bar.GetSize().Y * Thr;
	DrawRect(FLinearColor(0.55f, 1.f, 0.6f, PC->IsThrottleActive() ? 0.85f : 0.55f), Bar.Min.X, Bar.Max.Y - FillH, Bar.GetSize().X, FillH);
	DrawBox(Bar, HudGreen, T);
	DrawLabel(FString::Printf(TEXT("THR %3d%%"), FMath::RoundToInt(Thr * 100.f)), FVector2D(Bar.Max.X, Bar.Min.Y - 0.05f * H) - FVector2D(0.16f * H, 0.f), HudGreen, 1.3f * S);

	// Touch stick: ring + knob while held, a faint hint ring otherwise.
	if (PC->IsStickActive())
	{
		DrawCircle(PC->GetStickOrigin(), L.StickRadius, HudGreen, T);
		DrawCircle(PC->GetStickKnob(), 0.35f * L.StickRadius, HudGreen, 2.f * T);
	}
	else
	{
		const FVector2D Hint(0.17f * W, 0.72f * H);
		DrawCircle(Hint, L.StickRadius, HudDim, T);
		DrawLabel(TEXT("STICK"), Hint, HudDim, 1.2f * S, true);
	}
	if (!PC->IsThrottleActive())
	{
		DrawLabel(TEXT("SLIDE THROTTLE"), FVector2D(W - 0.24f * H, 0.70f * H), HudDim, 1.2f * S, true);
	}

	// Buttons.
	DrawButton(L.GfxButton, TEXT("GFX"), false, 1.4f * S, T);
	DrawRect(FLinearColor(0.f, 0.f, 0.f, 0.35f), L.ResetButton.Min.X, L.ResetButton.Min.Y, L.ResetButton.GetSize().X, L.ResetButton.GetSize().Y);
	DrawBox(L.ResetButton, HudGreen, T);
	DrawLabel(TEXT("RESET"), L.ResetButton.GetCenter(), HudGreen, 1.4f * S, true);
	DrawRect(FLinearColor(0.f, 0.f, 0.f, 0.35f), L.InvertButton.Min.X, L.InvertButton.Min.Y, L.InvertButton.GetSize().X, L.InvertButton.GetSize().Y);
	DrawBox(L.InvertButton, HudGreen, T);
	DrawLabel(PC->IsPitchInverted() ? TEXT("PITCH INV") : TEXT("PITCH STD"), L.InvertButton.GetCenter(), HudGreen, 1.2f * S, true);

	// Status (crash / out of area) and first-seconds help.
	if (Plane->GetStatusTimeLeft() > 0.f)
	{
		DrawLabel(Plane->GetStatusText(), FVector2D(0.5f * W, 0.30f * H), HudWarn, 2.f * S, true);
	}
	else if (PC->GetTimeSinceStart() < 12.f)
	{
		DrawLabel(TEXT("Left thumb: stick (pull down = climb)    Right thumb: slide throttle, sideways = rudder"),
			FVector2D(0.5f * W, 0.25f * H), FLinearColor::White, 1.2f * S, true);
	}
}

void AFreeFlightHUD::DrawButton(const FBox2D& B, const FString& Text, bool bActive, float Scale, float Thickness)
{
	DrawRect(bActive ? FLinearColor(0.20f, 0.55f, 0.28f, 0.85f) : FLinearColor(0.f, 0.f, 0.f, 0.45f), B.Min.X, B.Min.Y, B.GetSize().X, B.GetSize().Y);
	DrawBox(B, HudGreen, Thickness);
	DrawLabel(Text, B.GetCenter(), bActive ? FLinearColor::White : HudGreen, Scale, true);
}

void AFreeFlightHUD::DrawMenu(const AFreeFlightPlayerController* PC, float S, float T)
{
	const USkyfrontGameUserSettings* G = USkyfrontGameUserSettings::Get();
	if (!G)
	{
		return;
	}
	const auto& M = PC->GetMenuLayout();
	const float H = Canvas->SizeY;
	DrawRect(FLinearColor(0.02f, 0.03f, 0.03f, 0.78f), M.Panel.Min.X, M.Panel.Min.Y, M.Panel.GetSize().X, M.Panel.GetSize().Y);
	DrawBox(M.Panel, HudGreen, T);
	DrawLabel(FString::Printf(TEXT("GRAPHICS  -  %s"), USkyfrontGameUserSettings::PresetName(G->GetPreset())),
		FVector2D(M.Panel.Min.X + 0.03f * H, M.Panel.Min.Y + 0.03f * H), FLinearColor::White, 1.6f * S);
	static const TCHAR* Short[] = {TEXT("POWER SAVER"), TEXT("BALANCED"), TEXT("HIGH"), TEXT("ULTRA")};
	for (int32 i = 0; i < 4; ++i)
	{
		DrawButton(M.Presets[i], Short[i], G->GetPreset() == i, 1.15f * S, T);
	}
	for (int32 r = 0; r < USkyfrontGameUserSettings::NumRows; ++r)
	{
		DrawLabel(USkyfrontGameUserSettings::RowName(r), M.RowLabel[r], FLinearColor::White, 1.25f * S);
		const int32 L = G->GetRow(r), N = USkyfrontGameUserSettings::RowLevelCount(r);
		DrawButton(M.RowMinus[r], TEXT("<"), false, 1.6f * S, T);
		DrawButton(M.RowPlus[r], TEXT(">"), false, 1.6f * S, T);
		DrawLabel(G->RowValueText(r), M.RowValue[r], HudGreen, 1.35f * S, true);
		// level pips under the value
		for (int32 k = 0; k < N; ++k)
		{
			const float X = M.RowValue[r].X + (k - (N - 1) * 0.5f) * 0.03f * H, Y = M.RowValue[r].Y + 0.027f * H;
			DrawRect(k <= L ? HudGreen : FLinearColor(1.f, 1.f, 1.f, 0.25f), X - 0.009f * H, Y, 0.018f * H, 0.006f * H);
		}
	}
	DrawButton(M.Defaults, TEXT("DEFAULTS"), false, 1.3f * S, T);
	DrawButton(M.Diag, G->GetShowDiagnostics() ? TEXT("DIAG ON") : TEXT("DIAG OFF"), G->GetShowDiagnostics(), 1.3f * S, T);
	DrawButton(M.Close, TEXT("FLY"), false, 1.5f * S, T);
}

void AFreeFlightHUD::UpdateFrameStats()
{
	const float Ms = FApp::GetDeltaTime() * 1000.f;
	WinSumMs += Ms;
	WinWorstMs = FMath::Max(WinWorstMs, Ms);
	WinGpuSumMs += FPlatformTime::ToMilliseconds(RHIGetGPUFrameCycles(0));
	WinTime += FApp::GetDeltaTime();
	++WinFrames;
	if (WinTime >= 1.f)
	{
		AvgMs = WinSumMs / WinFrames;
		WorstMs = WinWorstMs;
		GpuMs = WinGpuSumMs / WinFrames;
		WinSumMs = WinWorstMs = WinGpuSumMs = WinTime = 0.f;
		WinFrames = 0;
	}
	if (const AFreeFlightPlayerController* PC = Cast<AFreeFlightPlayerController>(PlayerOwner))
	{
		if (PC->GetLastApplyTime() != SeenApplyTime)
		{
			SeenApplyTime = PC->GetLastApplyTime();
			WorstSinceApplyMs = 0.f;
		}
		if (FPlatformTime::Seconds() - SeenApplyTime < 3.0)
		{
			WorstSinceApplyMs = FMath::Max(WorstSinceApplyMs, Ms);   // hitch of the last settings change (first 3 s)
		}
	}
}

void AFreeFlightHUD::DrawDiagnostics(const AFreeFlightPlayerController* PC, float S)
{
	const USkyfrontGameUserSettings* G = USkyfrontGameUserSettings::Get();
	if (!G)
	{
		return;
	}
	CensusTimer -= FApp::GetDeltaTime();
	if (CensusTimer <= 0.f)
	{
		CensusTimer = 2.f;
		TreeComps = TreeCompsShown = BuildingComps = 0;
		TreeInst = TreeInstShown = 0;
		const int32 DetailMode = GetCachedScalabilityCVars().DetailMode;
		for (TObjectIterator<UHierarchicalInstancedStaticMeshComponent> It; It; ++It)
		{
			const UHierarchicalInstancedStaticMeshComponent* C = *It;
			if (C->GetWorld() != GetWorld() || !C->IsRegistered())
			{
				continue;
			}
			const UMaterialInterface* Mat = C->GetMaterial(0);
			if (Mat && Mat->GetName().Contains(TEXT("NF_Building")))
			{
				++BuildingComps;
				continue;
			}
			if (Mat && Mat->GetName().Contains(TEXT("FI_Impostor")))
			{
				continue;   // far-impostor layer (research), not a 3D tree band
			}
			++TreeComps;
			TreeInst += C->GetInstanceCount();
			if (C->DetailMode <= DetailMode)
			{
				++TreeCompsShown;
				TreeInstShown += C->GetInstanceCount();
			}
		}
	}

	const USkyfrontGameUserSettings::FEffective& E = G->GetEffective();
	const float H = Canvas->SizeY;
	const int32 Vw = Canvas->SizeX, Vh = Canvas->SizeY;
	const float Sp = E.ScreenPercentage / 100.f;
	const FString Profile = UDeviceProfileManager::Get().GetActiveDeviceProfileName();
	const FString Rhi = GDynamicRHI ? FString(GDynamicRHI->GetName()) : FString(TEXT("?"));
	const float Csf = IConsoleManager::Get().FindConsoleVariable(TEXT("r.MobileContentScaleFactor"))->GetFloat();
	TArray<FString> Lines;
	Lines.Add(FString::Printf(TEXT("FPS %.1f   frame %.1f ms (worst %.0f)   GPU %.1f ms   cap %d"), AvgMs > 0.f ? 1000.f / AvgMs : 0.f, AvgMs, WorstMs, GpuMs, E.FpsCap));
	Lines.Add(FString::Printf(TEXT("MODE %s   last change: apply %.0f ms, worst frame %.0f ms"), USkyfrontGameUserSettings::PresetName(G->GetPreset()), E.ApplyMs, WorstSinceApplyMs));
	Lines.Add(FString::Printf(TEXT("RES %dx%d scene (%.0f%% of %dx%d)   CSF %.2f"), FMath::RoundToInt(Vw * Sp), FMath::RoundToInt(Vh * Sp), E.ScreenPercentage, Vw, Vh, Csf));
	Lines.Add(FString::Printf(TEXT("TREES dissolve by %.1f km, HISM cull x%.2f (%.1f-%.1f km), WP load %.1f km"), E.TreeEndM / 1000.f, E.ViewDistanceScale,
		1.42f * E.ViewDistanceScale, 3.65f * E.ViewDistanceScale, E.WpLoadingRangeM / 1000.f));
	Lines.Add(FString::Printf(TEXT("FOREST DetailMode %d: %d/%d HISM, %lld/%lld trees shown"), E.DetailMode, TreeCompsShown, TreeComps, TreeInstShown, TreeInst));
	Lines.Add(FString::Printf(TEXT("TOWNS %.1f km (%d HISM)   foliage cap %s"), E.BuildingCullM / 1000.f, BuildingComps,
		E.MaxEndCullM > 0.f ? *FString::Printf(TEXT("%.1f km"), E.MaxEndCullM / 1000.f) : TEXT("off")));
	Lines.Add(FString::Printf(TEXT("SHADOW %s   AO %s   LANDSCAPE LOD x%.2f"),
		E.ShadowDistanceM > 0.f ? *FString::Printf(TEXT("%.0f m x%d %d"), E.ShadowDistanceM, E.Cascades, E.ShadowRes) : TEXT("off"),
		E.AoLevels > 0 ? TEXT("on") : TEXT("off"), E.LandscapeLodScale));
	Lines.Add(FString::Printf(TEXT("%s  %s"), *Profile, *Rhi));
	const float X = 0.03f * H;
	float Y = PC->IsMenuOpen() ? 0.03f * H : 0.19f * H;
	DrawRect(FLinearColor(0.f, 0.f, 0.f, 0.35f), X - 0.01f * H, Y - 0.005f * H, 0.70f * H, Lines.Num() * 0.027f * H + 0.01f * H);
	for (const FString& Line : Lines)
	{
		DrawLabel(Line, FVector2D(X, Y), FLinearColor(1.f, 0.95f, 0.6f, 1.f), 0.78f * S);
		Y += 0.027f * H;
	}
}
