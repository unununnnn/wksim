using UnrealBuildTool;
public class WksimVisual : ModuleRules
{
    public WksimVisual(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new string[] {
            "Core", "CoreUObject", "Engine", "InputCore", "Sockets", "Networking", "Json", "RenderCore"
        });
    }
}
