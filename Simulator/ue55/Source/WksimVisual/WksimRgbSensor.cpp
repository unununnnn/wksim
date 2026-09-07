#include "WksimRgbSensor.h"

#include "Async/Async.h"
#include "Components/SceneCaptureComponent2D.h"
#include "Engine/TextureRenderTarget2D.h"
#include "Engine/World.h"
#include "Dom/JsonObject.h"
#include "HAL/FileManager.h"
#include "IImageWrapper.h"
#include "IImageWrapperModule.h"
#include "Misc/DateTime.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Modules/ModuleManager.h"
#include "RHIGPUReadback.h"
#include "RenderingThread.h"
#include "Serialization/JsonSerializer.h"
#include <atomic>
#include <initializer_list>

struct FWksimRgbWork
{
    // State handoff is release/acquire; non-atomic payload has one owner at a time.
    std::atomic<bool> Cancelled{false}, PollQueued{false}, Done{false};
    TUniquePtr<FRHIGPUTextureReadback> Readback; // created/accessed/destroyed on render thread
    FWksimRgbConfig Config;
    FWksimRgbRequest Request;
    uint64 Frame = 0;
    FString CaptureUtc, CompletionUtc, MetadataPath, Error;
    TSharedPtr<IImageWrapper> Png;
};

namespace
{
bool ValidId(const FString& Id)
{
    if (Id.IsEmpty() || Id.Len() > 96) return false;
    for (TCHAR C : Id)
        if (!((C >= 'a' && C <= 'z') || (C >= 'A' && C <= 'Z') ||
              (C >= '0' && C <= '9') || C == '_' || C == '-')) return false;
    return true;
}

bool ValidPose(const FTransform& Pose)
{
    const FVector P = Pose.GetTranslation();
    const FQuat Q = Pose.GetRotation();
    return FMath::IsFinite(P.X) && FMath::IsFinite(P.Y) && FMath::IsFinite(P.Z) &&
        P.GetAbsMax() <= 1.e9 && FMath::IsFinite(Q.X) && FMath::IsFinite(Q.Y) &&
        FMath::IsFinite(Q.Z) && FMath::IsFinite(Q.W) && Q.IsNormalized() &&
        Pose.GetScale3D().Equals(FVector::OneVector, 1.e-6);
}

TArray<TSharedPtr<FJsonValue>> Numbers(std::initializer_list<double> Values)
{
    TArray<TSharedPtr<FJsonValue>> Result;
    for (double Value : Values) Result.Add(MakeShared<FJsonValueNumber>(Value));
    return Result;
}

TSharedPtr<FJsonObject> PoseJson(const FTransform& Pose)
{
    auto Json = MakeShared<FJsonObject>();
    const FVector P = Pose.GetTranslation();
    const FQuat Q = Pose.GetRotation();
    Json->SetArrayField(TEXT("position_cm"), Numbers({P.X, P.Y, P.Z}));
    Json->SetArrayField(TEXT("quaternion_xyzw"), Numbers({Q.X, Q.Y, Q.Z, Q.W}));
    return Json;
}

void SaveFrame(const TSharedPtr<FWksimRgbWork, ESPMode::ThreadSafe>& W, TArray<FColor> Pixels)
{
    if (W->Cancelled.load()) { W->Done.store(true); return; }
    const auto& C = W->Config;
    const FString Stem = FString::Printf(TEXT("%s_%s_%s_%s_%s_%llu"),
        *C.RunId, *C.InstanceId, *C.Epoch, *C.VehicleId, *C.SensorId, W->Frame);
    const FString PngPath = FPaths::Combine(C.OutputDirectory, Stem + TEXT(".png"));
    W->MetadataPath = FPaths::Combine(C.OutputDirectory, Stem + TEXT(".json"));
    const FString TempJson = W->MetadataPath + TEXT(".tmp");
    bool Ok = IFileManager::Get().MakeDirectory(*C.OutputDirectory, true);
    // A configuration owns a fresh directory; never silently overwrite another recording.
    Ok = Ok && !IFileManager::Get().FileExists(*PngPath) && !IFileManager::Get().FileExists(*W->MetadataPath);
    bool AttemptedPng = false;
    if (Ok && W->Png.IsValid() && W->Png->SetRaw(Pixels.GetData(),
        int64(Pixels.Num()) * sizeof(FColor), C.Width, C.Height, ERGBFormat::BGRA, 8))
    {
        TArray64<uint8> Bytes = W->Png->GetCompressed();
        Ok = !Bytes.IsEmpty() && !W->Cancelled.load();
        if (Ok)
        {
            // SaveArrayToFile can fail after creating a partial owned file.
            AttemptedPng = true;
            Ok = FFileHelper::SaveArrayToFile(Bytes, *PngPath);
        }
    }
    else Ok = false;
    W->CompletionUtc = FDateTime::UtcNow().ToIso8601();
    if (Ok && !W->Cancelled.load())
    {
        auto Json = MakeShared<FJsonObject>();
        Json->SetStringField(TEXT("schema"), TEXT("wksim.rgb.v1"));
        Json->SetStringField(TEXT("run_id"), C.RunId);
        Json->SetStringField(TEXT("instance_id"), C.InstanceId);
        Json->SetStringField(TEXT("epoch"), C.Epoch);
        Json->SetStringField(TEXT("vehicle_id"), C.VehicleId);
        Json->SetStringField(TEXT("sensor_id"), C.SensorId);
        // Decimal strings preserve integer identity beyond JSON's binary64 exact range.
        Json->SetStringField(TEXT("step"), LexToString(W->Request.Step));
        Json->SetStringField(TEXT("frame_id"), LexToString(W->Frame));
        Json->SetNumberField(TEXT("sim_time_seconds"), W->Request.SimTimeSeconds);
        Json->SetStringField(TEXT("capture_wall_utc"), W->CaptureUtc);
        Json->SetStringField(TEXT("completion_wall_utc"), W->CompletionUtc);
        Json->SetStringField(TEXT("capture_wall_semantics"), TEXT("game_thread_capture_submission; not GPU exposure timestamp"));
        Json->SetStringField(TEXT("completion_wall_semantics"), TEXT("PNG write complete before metadata publication"));
        Json->SetStringField(TEXT("image"), FPaths::GetCleanFilename(PngPath));
        Json->SetStringField(TEXT("encoding"), TEXT("png-rgba8-srgb"));
        Json->SetNumberField(TEXT("width"), C.Width);
        Json->SetNumberField(TEXT("height"), C.Height);
        Json->SetNumberField(TEXT("horizontal_fov_degrees"), C.HorizontalFovDegrees);
        const double Focal = C.Width / (2.0 * FMath::Tan(FMath::DegreesToRadians(double(C.HorizontalFovDegrees)) / 2.0));
        Json->SetArrayField(TEXT("K"), Numbers({Focal, 0, C.Width / 2.0, 0, Focal, C.Height / 2.0, 0, 0, 1}));
        Json->SetStringField(TEXT("pixel_coordinates"), TEXT("image edges at 0,width/height; pixel centers at index+0.5"));
        Json->SetArrayField(TEXT("distortion"), Numbers({0, 0, 0, 0, 0}));
        Json->SetStringField(TEXT("distortion_model"), TEXT("pinhole_zero_distortion_assumption"));
        Json->SetStringField(TEXT("pose_coordinates"), TEXT("UE world centimeters; X forward Y right Z up; optical x=Y y=-Z z=X"));
        Json->SetObjectField(TEXT("camera_world_pose"), PoseJson(W->Request.CameraWorldPose));
        Json->SetObjectField(TEXT("camera_in_vehicle"), PoseJson(C.CameraInVehicle));
        FString Text;
        const auto Writer = TJsonWriterFactory<>::Create(&Text);
        Ok = FJsonSerializer::Serialize(Json, Writer) &&
            FFileHelper::SaveStringToFile(Text, *TempJson, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM) &&
            !W->Cancelled.load() && IFileManager::Get().Move(*W->MetadataPath, *TempJson, false);
    }
    if (!Ok || W->Cancelled.load())
    {
        IFileManager::Get().Delete(*TempJson);
        if (AttemptedPng) { IFileManager::Get().Delete(*PngPath); IFileManager::Get().Delete(*W->MetadataPath); }
        if (!W->Cancelled.load()) W->Error = TEXT("RGB PNG/metadata write failed or output name already exists");
    }
    W->Done.store(true);
}
}

UWksimRgbSensor::UWksimRgbSensor()
{
    PrimaryComponentTick.bCanEverTick = false; // explicit Poll keeps integration ordering visible
}

bool UWksimRgbSensor::Configure(const FWksimRgbConfig& C, FString& Error)
{
    check(IsInGameThread());
    Error.Reset();
    if (Work) { Error = TEXT("RGB pending work must be drained with Poll before reconfiguration"); return false; }
    bConfigured = false;
    if (!ValidId(C.RunId) || !ValidId(C.InstanceId) || !ValidId(C.Epoch) ||
        !ValidId(C.VehicleId) || !ValidId(C.SensorId) || C.Width < 16 || C.Height < 16 ||
        C.Width > 4096 || C.Height > 4096 || int64(C.Width) * C.Height > 4194304 ||
        !FMath::IsFinite(C.HorizontalFovDegrees) || C.HorizontalFovDegrees < 5 || C.HorizontalFovDegrees > 150 ||
        !ValidPose(C.CameraInVehicle) || C.OutputDirectory.IsEmpty() || FPaths::IsRelative(C.OutputDirectory))
    { Error = TEXT("Invalid RGB identity, dimensions, FOV, unit extrinsics or absolute output directory"); return false; }
    if (!GetWorld() || !GetWorld()->Scene || !GetOwner())
    { Error = TEXT("RGB requires a registered owner in a rendering world"); return false; }
    if (!Capture)
    {
        Capture = NewObject<UWksimRgbCapture>(GetOwner(), NAME_None, RF_Transient);
        Capture->bCaptureEveryFrame = false;
        Capture->bCaptureOnMovement = false;
        Capture->bAlwaysPersistRenderingState = false;
        Capture->bRenderInMainRenderer = false;
        Capture->bMainViewFamily = false;
        Capture->bMainViewResolution = false;
        Capture->bMainViewCamera = false;
        Capture->bIgnoreScreenPercentage = true;
        Capture->CaptureSource = SCS_FinalColorLDR;
        Capture->ShowFlags.SetMotionBlur(false);
        Capture->ShowFlags.SetTemporalAA(false);
        Capture->PostProcessBlendWeight = 0;
        Capture->RegisterComponent();
    }
    Target = NewObject<UTextureRenderTarget2D>(this, NAME_None, RF_Transient);
    Target->bAutoGenerateMips = false;
    Target->InitCustomFormat(C.Width, C.Height, PF_B8G8R8A8, false);
    Capture->TextureTarget = Target;
    Capture->FOVAngle = C.HorizontalFovDegrees;
    Config = C;
    // Load module on game thread; only the per-frame wrapper crosses to the worker.
    FModuleManager::LoadModuleChecked<IImageWrapperModule>(TEXT("ImageWrapper"));
    LastStep = -1;
    LastSimTime = -1;
    bConfigured = true;
    return true;
}

bool UWksimRgbSensor::RequestCapture(const FWksimRgbRequest& R, FString& Error)
{
    check(IsInGameThread());
    Error.Reset();
    if (!bConfigured || R.RunId != Config.RunId || R.InstanceId != Config.InstanceId || R.Epoch != Config.Epoch)
    { ++DroppedStale; Error = TEXT("RGB unconfigured or stale identity"); return false; }
    if (R.Step < 0 || R.Step <= LastStep || !FMath::IsFinite(R.SimTimeSeconds) ||
        R.SimTimeSeconds < 0 || R.SimTimeSeconds < LastSimTime || !ValidPose(R.CameraWorldPose))
    { Error = TEXT("Invalid or repeated RGB authoritative step/time/pose"); return false; }
    if (Work) { ++DroppedBusy; Error = TEXT("RGB dropped: one capture/readback/write already in flight"); return false; }
    if (!Capture->IsRegistered() || !Capture->IsVisible() || Capture->IsDetailCulled() || !GetWorld()->Scene)
    { ++Failed; Error = TEXT("RGB scene capture unavailable or culled"); return false; }
    Capture->SetWorldTransform(R.CameraWorldPose);
    Work = MakeShared<FWksimRgbWork, ESPMode::ThreadSafe>();
    Work->Config = Config;
    Work->Request = R;
    Work->Request.CameraWorldPose = Capture->GetComponentTransform();
    Work->Frame = ++Frame;
    Work->CaptureUtc = FDateTime::UtcNow().ToIso8601();
    Work->Png = FModuleManager::GetModuleChecked<IImageWrapperModule>(TEXT("ImageWrapper")).CreateImageWrapper(EImageFormat::PNG);
    LastStep = R.Step;
    LastSimTime = R.SimTimeSeconds;
    // CaptureScene snapshots view and enqueues its rendering before our staging copy.
    Capture->CaptureScene();
    FTextureRenderTargetResource* Resource = Target->GameThread_GetRenderTargetResource();
    const auto W = Work;
    ENQUEUE_RENDER_COMMAND(WksimRgbCopy)([W, Resource](FRHICommandListImmediate& RHICmdList)
    {
        if (!Resource || !Resource->GetRenderTargetTexture())
        { W->Error = TEXT("RGB render target unavailable"); W->Done.store(true); return; }
        W->Readback = MakeUnique<FRHIGPUTextureReadback>(TEXT("WksimRgb"));
        FRHITexture* Texture = Resource->GetRenderTargetTexture();
        // EnqueueCopy transitions its staging destination, not the source texture.
        RHICmdList.Transition(FRHITransitionInfo(Texture, ERHIAccess::Unknown, ERHIAccess::CopySrc));
        W->Readback->EnqueueCopy(RHICmdList, Texture);
        RHICmdList.Transition(FRHITransitionInfo(Texture, ERHIAccess::CopySrc, ERHIAccess::SRVMask));
    });
    return true;
}

bool UWksimRgbSensor::Poll(FString& MetadataPath, FString& Error)
{
    check(IsInGameThread());
    MetadataPath.Reset(); Error.Reset();
    if (!Work) return false;
    const auto W = Work;
    if (W->Done.load())
    {
        const bool Current = !W->Cancelled.load() && bConfigured && W->Request.Epoch == Config.Epoch;
        if (Current) { Error = W->Error; if (Error.IsEmpty()) MetadataPath = W->MetadataPath; else ++Failed; }
        else ++DroppedStale;
        Work.Reset();
        return Current && Error.IsEmpty() && !MetadataPath.IsEmpty();
    }
    if (W->PollQueued.exchange(true)) return false;
    ENQUEUE_RENDER_COMMAND(WksimRgbPoll)([W](FRHICommandListImmediate& RHICmdList)
    {
        if (!W->Readback || !W->Readback->IsReady()) { W->PollQueued.store(false); return; }
        if (W->Cancelled.load()) { W->Readback.Reset(); W->Done.store(true); return; }
        int32 Pitch = 0, BufferHeight = 0;
        const void* Data = W->Readback->Lock(Pitch, &BufferHeight);
        TArray<FColor> Pixels;
        if (Data && Pitch >= W->Config.Width && BufferHeight >= W->Config.Height)
        {
            Pixels.SetNumUninitialized(W->Config.Width * W->Config.Height);
            for (int32 Y = 0; Y < W->Config.Height; ++Y)
                FMemory::Memcpy(Pixels.GetData() + Y * W->Config.Width,
                    static_cast<const uint8*>(Data) + int64(Y) * Pitch * sizeof(FColor), W->Config.Width * sizeof(FColor));
            for (FColor& Pixel : Pixels) Pixel.A = 255;
        }
        if (Data) W->Readback->Unlock();
        W->Readback.Reset();
        if (Pixels.IsEmpty()) { W->Error = TEXT("RGB invalid GPU staging layout"); W->Done.store(true); return; }
        // PollQueued remains true until worker completion: no unbounded polling or IO queue.
        Async(EAsyncExecution::ThreadPool, [W, Pixels = MoveTemp(Pixels)]() mutable { SaveFrame(W, MoveTemp(Pixels)); });
    });
    return false;
}

void UWksimRgbSensor::Invalidate()
{
    check(IsInGameThread());
    bConfigured = false;
    if (Work) Work->Cancelled.store(true);
}

void UWksimRgbSensor::EndPlay(const EEndPlayReason::Type Reason)
{
    Invalidate();
    // Final queued cleanup owns pending staging resource; no UObject is accessed there.
    if (Work)
    {
        const auto W = Work;
        ENQUEUE_RENDER_COMMAND(WksimRgbRelease)([W](FRHICommandListImmediate& RHICmdList) { W->Readback.Reset(); });
        Work.Reset();
    }
    if (Capture) Capture->DestroyComponent();
    Super::EndPlay(Reason);
}
