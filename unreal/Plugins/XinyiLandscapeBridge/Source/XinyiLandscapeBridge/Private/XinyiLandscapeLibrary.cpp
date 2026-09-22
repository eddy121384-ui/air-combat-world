#include "XinyiLandscapeLibrary.h"

#include "Editor.h"
#include "EngineUtils.h"
#include "HAL/FileManager.h"
#include "Json.h"
#include "Landscape.h"
#include "LandscapeInfo.h"
#include "LandscapeProxy.h"
#include "Misc/FileHelper.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

namespace
{
FString JsonString(const TSharedRef<FJsonObject>& Object)
{
    FString Out;
    const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Out);
    FJsonSerializer::Serialize(Object, Writer);
    return Out;
}

TSharedRef<FJsonObject> Failure(const FString& Reason)
{
    const TSharedRef<FJsonObject> Object = MakeShared<FJsonObject>();
    Object->SetBoolField(TEXT("pass"), false);
    Object->SetStringField(TEXT("status"), TEXT("FAIL"));
    Object->SetStringField(TEXT("reason"), Reason);
    return Object;
}

UWorld* EditorWorld()
{
    if (!GEditor)
    {
        return nullptr;
    }
    return GEditor->GetEditorWorldContext().World();
}

ALandscape* FindLandscapeByLabel(UWorld* World, const FString& ActorLabel)
{
    if (!World)
    {
        return nullptr;
    }

    for (TActorIterator<ALandscape> It(World); It; ++It)
    {
        ALandscape* Landscape = *It;
        if (IsValid(Landscape) && Landscape->GetActorLabel() == ActorLabel)
        {
            return Landscape;
        }
    }
    return nullptr;
}

void AddVector(TSharedRef<FJsonObject> Object, const TCHAR* Name, const FVector& Value)
{
    TArray<TSharedPtr<FJsonValue>> Values;
    Values.Add(MakeShared<FJsonValueNumber>(Value.X));
    Values.Add(MakeShared<FJsonValueNumber>(Value.Y));
    Values.Add(MakeShared<FJsonValueNumber>(Value.Z));
    Object->SetArrayField(Name, Values);
}

TSharedRef<FJsonObject> LandscapeSummary(ALandscape* Landscape)
{
    if (!IsValid(Landscape))
    {
        return Failure(TEXT("landscape is null or invalid"));
    }

    const TSharedRef<FJsonObject> Object = MakeShared<FJsonObject>();
    Object->SetBoolField(TEXT("pass"), true);
    Object->SetStringField(TEXT("status"), TEXT("PASS"));
    Object->SetStringField(TEXT("label"), Landscape->GetActorLabel());
    Object->SetStringField(TEXT("path"), Landscape->GetPathName());
    Object->SetNumberField(TEXT("component_count"), Landscape->LandscapeComponents.Num());
    Object->SetNumberField(TEXT("num_subsections"), Landscape->NumSubsections);
    Object->SetNumberField(TEXT("subsection_size_quads"), Landscape->SubsectionSizeQuads);
    Object->SetNumberField(TEXT("component_size_quads"), Landscape->ComponentSizeQuads);

    AddVector(Object, TEXT("location_cm"), Landscape->GetActorLocation());
    AddVector(Object, TEXT("scale_xyz"), Landscape->GetActorScale3D());

    const FBox Bounds = Landscape->GetComponentsBoundingBox(true);
    AddVector(Object, TEXT("bounds_min_cm"), Bounds.Min);
    AddVector(Object, TEXT("bounds_max_cm"), Bounds.Max);

    ULandscapeInfo* Info = Landscape->GetLandscapeInfo();
    Object->SetBoolField(TEXT("landscape_info_valid"), IsValid(Info));
    if (IsValid(Info))
    {
        int32 MinX = 0;
        int32 MinY = 0;
        int32 MaxX = 0;
        int32 MaxY = 0;
        const bool bHasExtent = Info->GetLandscapeExtent(MinX, MinY, MaxX, MaxY);
        Object->SetBoolField(TEXT("has_landscape_extent"), bHasExtent);
        if (bHasExtent)
        {
            TArray<TSharedPtr<FJsonValue>> Extent;
            Extent.Add(MakeShared<FJsonValueNumber>(MinX));
            Extent.Add(MakeShared<FJsonValueNumber>(MinY));
            Extent.Add(MakeShared<FJsonValueNumber>(MaxX));
            Extent.Add(MakeShared<FJsonValueNumber>(MaxY));
            Object->SetArrayField(TEXT("landscape_extent_quads"), Extent);
        }
    }

    return Object;
}
} // namespace

FString UXinyiLandscapeLibrary::CreateLandscapeFromRaw16(
    const FString& Raw16Path,
    const int32 SizeX,
    const int32 SizeY,
    const int32 NumSubsections,
    const int32 SubsectionSizeQuads,
    const FVector LocationCm,
    const FVector ScaleXYZ,
    const FString& ActorLabel)
{
#if !WITH_EDITOR
    return JsonString(Failure(TEXT("XinyiLandscapeBridge is editor-only")));
#else
    if (SizeX <= 1 || SizeY <= 1 || NumSubsections <= 0 || SubsectionSizeQuads <= 0)
    {
        return JsonString(Failure(TEXT("invalid landscape dimensions/topology")));
    }

    const int32 ComponentSizeQuads = NumSubsections * SubsectionSizeQuads;
    if (((SizeX - 1) % ComponentSizeQuads) != 0 || ((SizeY - 1) % ComponentSizeQuads) != 0)
    {
        return JsonString(Failure(FString::Printf(
            TEXT("heightmap dimensions %dx%d do not align to component size %d quads"),
            SizeX, SizeY, ComponentSizeQuads)));
    }

    const int32 ComponentsX = (SizeX - 1) / ComponentSizeQuads;
    const int32 ComponentsY = (SizeY - 1) / ComponentSizeQuads;
    const int32 ExpectedComponents = ComponentsX * ComponentsY;

    TArray<uint8> Bytes;
    if (!FFileHelper::LoadFileToArray(Bytes, *Raw16Path))
    {
        return JsonString(Failure(FString::Printf(TEXT("failed to read RAW16: %s"), *Raw16Path)));
    }

    const int64 ExpectedSamples = static_cast<int64>(SizeX) * static_cast<int64>(SizeY);
    const int64 ExpectedBytes = ExpectedSamples * 2;
    if (Bytes.Num() != ExpectedBytes)
    {
        return JsonString(Failure(FString::Printf(
            TEXT("RAW16 byte count mismatch: got %d expected %lld"),
            Bytes.Num(), ExpectedBytes)));
    }

    TArray<uint16> HeightData;
    HeightData.SetNumUninitialized(ExpectedSamples);
    for (int64 Index = 0; Index < ExpectedSamples; ++Index)
    {
        const uint16 Lo = static_cast<uint16>(Bytes[Index * 2]);
        const uint16 Hi = static_cast<uint16>(Bytes[Index * 2 + 1]);
        HeightData[Index] = static_cast<uint16>(Lo | (Hi << 8));
    }

    UWorld* World = EditorWorld();
    if (!World)
    {
        return JsonString(Failure(TEXT("no current editor world")));
    }

    if (FindLandscapeByLabel(World, ActorLabel))
    {
        return JsonString(Failure(FString::Printf(
            TEXT("landscape label already exists: %s"), *ActorLabel)));
    }

    FActorSpawnParameters SpawnParameters;
    ALandscape* Landscape = World->SpawnActor<ALandscape>(SpawnParameters);
    if (!IsValid(Landscape))
    {
        return JsonString(Failure(TEXT("World->SpawnActor<ALandscape> failed")));
    }

    Landscape->SetActorLabel(ActorLabel);
    Landscape->bCanHaveLayersContent = false;
    Landscape->SetActorLocation(LocationCm);
    Landscape->SetActorScale3D(ScaleXYZ);

    TMap<FGuid, TArray<uint16>> HeightDataPerLayers;
    HeightDataPerLayers.Add(FGuid(), MoveTemp(HeightData));

    TMap<FGuid, TArray<FLandscapeImportLayerInfo>> MaterialLayerDataPerLayers;
    MaterialLayerDataPerLayers.Add(FGuid(), TArray<FLandscapeImportLayerInfo>());

    const TArrayView<const FLandscapeLayer> ImportLayers;
    Landscape->Import(
        FGuid::NewGuid(),
        0,
        0,
        SizeX - 1,
        SizeY - 1,
        NumSubsections,
        SubsectionSizeQuads,
        HeightDataPerLayers,
        nullptr,
        MaterialLayerDataPerLayers,
        ELandscapeImportAlphamapType::Additive,
        ImportLayers);

    Landscape->RegisterAllComponents();

    ULandscapeInfo* LandscapeInfo = Landscape->GetLandscapeInfo();
    if (!IsValid(LandscapeInfo))
    {
        LandscapeInfo = Landscape->CreateLandscapeInfo(false, true);
    }

    if (IsValid(LandscapeInfo))
    {
        LandscapeInfo->UpdateLayerInfoMap(Landscape, false);
    }

    Landscape->PostEditChange();
    Landscape->MarkPackageDirty();

    const int32 ActualComponents = Landscape->LandscapeComponents.Num();
    if (ActualComponents != ExpectedComponents)
    {
        const FString Reason = FString::Printf(
            TEXT("component count mismatch after import: got %d expected %d"),
            ActualComponents, ExpectedComponents);
        Landscape->Destroy();
        return JsonString(Failure(Reason));
    }

    TSharedRef<FJsonObject> Result = LandscapeSummary(Landscape);
    Result->SetStringField(TEXT("status"), TEXT("PASS_CREATED"));
    Result->SetNumberField(TEXT("size_x"), SizeX);
    Result->SetNumberField(TEXT("size_y"), SizeY);
    Result->SetNumberField(TEXT("components_x"), ComponentsX);
    Result->SetNumberField(TEXT("components_y"), ComponentsY);
    Result->SetStringField(TEXT("raw16_path"), Raw16Path);
    return JsonString(Result);
#endif
}

FString UXinyiLandscapeLibrary::InspectLandscapeByLabel(const FString& ActorLabel)
{
#if !WITH_EDITOR
    return JsonString(Failure(TEXT("XinyiLandscapeBridge is editor-only")));
#else
    UWorld* World = EditorWorld();
    if (!World)
    {
        return JsonString(Failure(TEXT("no current editor world")));
    }

    ALandscape* Landscape = FindLandscapeByLabel(World, ActorLabel);
    if (!Landscape)
    {
        return JsonString(Failure(FString::Printf(
            TEXT("landscape not found: %s"), *ActorLabel)));
    }

    TSharedRef<FJsonObject> Result = LandscapeSummary(Landscape);
    Result->SetStringField(TEXT("status"), TEXT("PASS_INSPECT"));
    return JsonString(Result);
#endif
}
