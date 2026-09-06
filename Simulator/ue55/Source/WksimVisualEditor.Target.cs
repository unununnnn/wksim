using UnrealBuildTool;
public class WksimVisualEditorTarget : TargetRules
{
    public WksimVisualEditorTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Editor;
        DefaultBuildSettings = BuildSettingsVersion.V5;
        IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_5;
        ExtraModuleNames.Add("WksimVisual");
    }
}
