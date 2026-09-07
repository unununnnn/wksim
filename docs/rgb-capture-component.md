# Native RGB capture component

`Simulator/ue55/Source/WksimVisual/WksimRgbSensor.{h,cpp}` implements a transient UE 5.5 SceneCapture2D camera, a BGRA8 render target, asynchronous GPU staging readback, and worker-thread PNG/JSON persistence. It does not capture the desktop or player viewport. No persistent UE assets or installed engine files are modified.

## Integration contract

Add `RHI` and `ImageWrapper` to WksimVisual.Build.cs dependencies. Existing Engine, RenderCore, Core and Json dependencies cover the remaining APIs. The component has no automatic tick and no callbacks.

1. Create `UWksimRgbSensor` with the owning actor as outer, retain it in a UPROPERTY, and register it. Call `Configure` on the game thread after the rendering world exists. Supply a fresh absolute recording directory and filename-safe ASCII run/instance/epoch/vehicle/sensor IDs (1–96 alphanumeric, underscore or hyphen). Width/height are 16–4096 with at most 4,194,304 pixels; horizontal FOV is 5–150 degrees.
2. Apply the accepted authoritative state to **all relevant scene actors**. Compute `CameraWorldPose = CameraInVehicle * VehicleWorldPose` using UE transform composition, after conversion at the UE boundary. The component accepts and reports UE world centimeters, +X forward, +Y right, +Z up. It does not silently convert ENU/NED or infer authoritative time from wall time.
3. Call `RequestCapture` with the actual applied run/instance/epoch, step, model time and camera world pose. It snapshots the actual capture component transform after applying this pose. Step must strictly increase across admitted captures; simulation time cannot decrease. A busy request is dropped immediately and increments `DroppedBusy`; it is never queued.
4. Call `Poll` each game tick even when there is no new state. A true result contains a finished **current-generation** metadata path. Dispatch only that result to a consumer. An error increments `Failed`. A slow consumer must not execute on the game thread or feed an acknowledgment into physics pacing.
5. On reset, disconnect or epoch change call `Invalidate` immediately. Continue `Poll` until `IsBusy()` becomes false, then configure the new identity and accept only newly applied current-epoch states. Never replay a recording directory to implement reconnect. Invalidation cancels publication without synchronously waiting for GPU or disk.
6. Call normal actor/component EndPlay on shutdown; the component invalidates work and releases render resources with queued render commands. A destroyed/recreated sensor must use a fresh output directory: frame IDs are process/component local and existing filenames are refused.

There is one in-flight job across capture, readback, encoding and disk write. One render polling command is outstanding at most. A hung GPU or filesystem therefore stops further RGB captures, with observable busy drops; it does not produce an unbounded work queue. Rendering and filesystem work still consume shared host resources, so this is not a guarantee against host resource exhaustion. This component neither invokes nor waits on the separate physics process.

## Image and time interpretation

The PNG contains opaque RGBA8 final LDR color. JSON contains original run/instance/epoch/vehicle/sensor identity, decimal-string step/frame IDs, model time, image dimensions and encoding, horizontal FOV, actual camera world pose, and configured mounting transform. The optical axes are x=UE camera Y, y=-UE camera Z, z=UE camera X.

For width W and horizontal FOV h, `fx = fy = W / (2 tan(h/2))`, `cx = W/2`, `cy = H/2`. K is flattened row-major. Image coordinates use edges at zero and W/H, with pixel centers at index+0.5. Distortion is explicitly an ideal pinhole zero-distortion assumption. Motion blur and temporal AA are disabled; no distortion blendable is installed by this component. Scene-wide postprocess/view extensions must be controlled by the acceptance scene, because external rendering extensions can invalidate ideal calibration.

`capture_wall_utc` is the game-thread submission timestamp, not an asserted GPU exposure timestamp. `completion_wall_utc` is taken after PNG writing and before metadata publication. Neither wall clock is substituted for `sim_time_seconds`. The metadata file is published by renaming a temporary JSON after PNG writing. Consumers must accept only current identity and notifications returned by `Poll`, not arbitrary filesystem discovery. Cancellation racing or following the worker's final check can leave correctly tagged but undelivered old-epoch files on disk; old-epoch completions never return from `Poll`. Failed writes attempt to remove their own partial PNG/metadata files. Historical files already delivered before invalidation remain historical evidence, not a current frame feed.

## Primary API and ordering evidence

Inspected installed UE 5.5 source under `E:/ue5.5/files/UE_5.5/Engine/Source`:

- `Runtime/Engine/Private/Components/SceneCaptureComponent.cpp`, `USceneCaptureComponent2D::CaptureScene`: sends deferred end-of-frame scene updates and immediately calls scene capture contents update when world, visibility and detail-mode gates permit. The component checks those gates before admission.
- `Runtime/Renderer/Private/SceneCaptureRendering.cpp`, `FScene::UpdateSceneCaptureContents`: reads the capture component transform and constructs the view on the game thread, then enqueues `CaptureCommand`. The camera disables capture-on-movement, every-frame capture, main-view camera/resolution, and rendering in the main renderer. The staging-copy command is enqueued only after `CaptureScene` returns; no subsequent capture is admitted until completion. The renderer's projection helper fixes horizontal scale to 1 and vertical scale to width/height, matching K above.
- `Runtime/RHI/Public/RHIGPUReadback.h`: texture `EnqueueCopy`, `IsReady`, `Lock(int32& OutRowPitchInPixels, int32* OutBufferHeight)`, `Unlock`. Poll and map occur on the render thread only after the GPU fence is ready; rows are copied using returned pitch, not assumed tight packing. No FlushRenderingCommands, ReadPixels or GPU wait is used.
- `Runtime/Engine/Private/TextureRenderTarget2D.cpp`: `InitCustomFormat` calls `UpdateResource`. `Runtime/ImageWrapper/Public/IImageWrapperModule.h` and `IImageWrapper.h` provide PNG wrapper creation, BGRA8 SetRaw and compressed bytes. `Core/Public/Misc/FileHelper.h` provides TArray64 PNG writes.

This establishes capture-view snapshot and render-command ordering for the installed implementation. It cannot establish that a caller applied the claimed authoritative step, that all moving world objects correspond to that step, or that a scene extension did not override rendering. Those obligations need integration and actual pose/occlusion evidence. `CaptureScene` may perform CPU scene-update work; asynchronous staging eliminates an explicit GPU wait, not all game-thread work or engine-internal CPU scheduling.

## Verification status

Source/API inspection and `git diff --check` were performed. No UE build or runtime was started by this implementation slice because the main agent owns resource scheduling. No sensor acceptance claim follows from source inspection. Required next verification: build with installed UE 5.5; fixed geometric target at known poses and occlusions; inspect real PNGs against K; exercise busy drops, disk failure, disconnect/reconnect and epoch invalidation; verify physics progress independently while image consumption stops.

Small independent intrinsics sanity check (PowerShell; 640x480, 90-degree horizontal FOV):

```powershell
$rgbFocal = 640 / (2 * [Math]::Tan([Math]::PI / 4))
if ([Math]::Abs($rgbFocal - 320) -gt 1e-9) { throw 'RGB focal check failed' }
$rgbRightEdge = $rgbFocal * 1 + 320
if ([Math]::Abs($rgbRightEdge - 640) -gt 1e-9) { throw 'RGB projection check failed' }
```

This checks the declared ideal projection only, not image generation or acceptance.


## Product integration and actual run

`View(..., joint_instance=..., rgb_config=...)` now writes the validated optional camera configuration for GameMode. The JSON uses version 1, vehicle_id, sensor_id, width/height, horizontal_fov_degrees, position_cm/quaternion_xyzw in UE vehicle coordinates, interval_steps and a separate localhost notify_port. View supplies its own fresh output directory. `Simulator.ue55.rgb.Reader` receives only notifications for an explicitly selected authoritative epoch/generation; it never scans recordings for live delivery.

The real two-FC ground run, PNG decoding, physical-pose/clock audit, consumer outage and reconnect are documented in [the integration report](2026-09-07-independent-rgb-report.md). This updates the earlier build-only status above. Projection/occlusion calibration, airborne image flows and real cold-reset acceptance remain open.


## Producer restart identity (v2)

Live metadata/notifications now use `wksim.rgb.v2` / `wksim.rgb-ready.v2` and require `stream_id`, a fresh 32-character lowercase-hex identity for each View. The physical manager instance, epoch and authoritative step remain separate. `FWksimRgbConfig` and `FWksimRgbRequest` require that stream identity; `Reader(..., stream_id=view.rgb_stream_id)` is bound to it and does not learn identity from received datagrams. Reopening a consumer for the same live View keeps that identity; reopening UE creates a new one. Filenames are `rgb_<stream_id>_<frame>.png/json`, keeping path components bounded even with long user sensor/run names. Historical v1 records remain auditable as historical evidence, but the current live Reader does not accept them.

Unit rejection of a retired producer within the same physical epoch is verified. Actual producer restart and cold-reset validation are still required before closing the complete camera lifecycle criteria.


## Explicit camera producer control

`View.set_rgb_enabled(False/True)` uses a separate, identity-bound UDP camera command. It cannot issue flight or physical-step commands. Disable invalidates pending delivery immediately; enable selects a fresh stream ID and requires a later authority step before capture. Acknowledgment means configuration accepted; completion still requires observed native PNG output. Scene generation, epoch, old stream ID and increasing request sequence are checked by UE. A new Reader must bind to the acknowledged stream ID.

The first actual stop/start/cold-reset run retained a UE D3D12 render-thread access violation after restart, during physical cold reset. It is failed evidence (`validation/rgb-lifecycle-20260907-run1`). Reconfiguration now retains its render-target UObject/resource, using the engine's `ResizeTarget` only for changed dimensions. This is a candidate correction pending a fresh complete real run; no claim that the crash cause or lifecycle acceptance is yet settled.
