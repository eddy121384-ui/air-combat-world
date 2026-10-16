#include "XinyiWorldPartitionAuditLibrary.h"

#include "Dom/JsonObject.h"
#include "Editor.h"
#include "Engine/World.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "WorldPartition/WorldPartition.h"

FString UXinyiWorldPartitionAuditLibrary::InspectCurrentEditorWorldPartition()
{
    const TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();

#if WITH_EDITOR
    UWorld* World = GEditor ? GEditor->GetEditorWorldContext().World() : nullptr;
    if (!World)
    {
        Result->SetStringField(TEXT("status"), TEXT("FAIL_NO_EDITOR_WORLD"));
    }
    else
    {
        UWorldPartition* Partition = World->GetWorldPartition();
        Result->SetStringField(TEXT("status"), TEXT("PASS"));
        Result->SetStringField(TEXT("world_path"), World->GetPathName());
        Result->SetBoolField(TEXT("present"), Partition != nullptr);
        if (Partition)
        {
            Result->SetBoolField(TEXT("initialized"), Partition->IsInitialized());
            Result->SetBoolField(TEXT("supports_streaming"), Partition->SupportsStreaming());
            Result->SetBoolField(TEXT("enable_streaming"), Partition->IsStreamingEnabled());
            Result->SetBoolField(TEXT("streaming_enabled_in_editor"), Partition->IsStreamingEnabledInEditor());
            Result->SetBoolField(TEXT("can_stream"), Partition->CanStream());
        }
    }
#else
    Result->SetStringField(TEXT("status"), TEXT("FAIL_EDITOR_ONLY"));
#endif

    FString Out;
    const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Out);
    FJsonSerializer::Serialize(Result, Writer);
    return Out;
}
