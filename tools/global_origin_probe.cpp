// Read-only probe of the admitted model using its actual generated header.
// No vendor source/header is copied into the repository.
#include "Exp1_MinModelTemp.h"
#include <dlfcn.h>
#include <iomanip>
#include <iostream>

int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    void *library = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    if (!library) { std::cerr << dlerror() << '\n'; return 3; }
    auto create = reinterpret_cast<void *(*)()>(dlsym(library, "wk_model_create"));
    auto destroy = reinterpret_cast<void (*)(void *)>(dlsym(library, "wk_model_destroy"));
    auto parameters = static_cast<const P_Exp1_MinModelTemp_T *>(
        dlsym(library, "_ZN21MulticopterModelClass19Exp1_MinModelTemp_PE"));
    if (!create || !destroy || !parameters) { dlclose(library); return 4; }
    void *model = create();
    if (!model) { dlclose(library); return 5; }
    std::cout << std::setprecision(17)
        << "{\"latitude_deg\":" << parameters->ModelParam_GPSLatLong[0]
        << ",\"longitude_deg\":" << parameters->ModelParam_GPSLatLong[1]
        << ",\"alt_amsl_m\":" << -parameters->ModelParam_envAltitude
        << ",\"env_altitude_parameter_m\":" << parameters->ModelParam_envAltitude << "}\n";
    destroy(model);
    dlclose(library);
    return 0;
}
