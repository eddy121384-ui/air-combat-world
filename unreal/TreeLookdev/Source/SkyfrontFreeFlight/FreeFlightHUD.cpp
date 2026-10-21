#include "FreeFlightHUD.h"

#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Engine/Font.h"
#include "FreeFlightPawn.h"
#include "FreeFlightPlayerController.h"

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
