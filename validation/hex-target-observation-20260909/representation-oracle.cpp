// Recording-only arithmetic oracle from the pinned AP Location/Guided/GCS source.
// SITL has HAL_WITH_POSTYPE_DOUBLE=1 and HAL_WITH_EKF_DOUBLE=1.
#include <cmath>
#include <cstdint>
#include <cstdio>
int main() {
    const int32_t lat = double(40.1540571)*1E7, lng = double(116.2593918)*1E7;
    const int32_t home_alt=4997, origin_alt=5000, origin_lat=401540302, origin_lng=1162593683;
    const int32_t alt_cm = double(float(3))*100.0;
    const auto scale=[](int32_t v) { return std::fmax(std::cos(v*(1.0e-7*(M_PI/180.0f))),0.01); };
    double north=(lat-origin_lat)*1.1131884502145034;
    double east=(lng-origin_lng)*1.1131884502145034*scale((lat+origin_lat)/2);
    north*=0.01; east*=0.01;
    const float origin_alt_m=(home_alt+alt_cm-origin_alt)*0.01;
    const double down=-origin_alt_m;
    const double neu_x_cm=north*100.0, neu_y_cm=east*100.0, neu_z_cm=-down*100.0;
    const float inverse=89.83204953368922;
    const int32_t dlat=(neu_x_cm*0.01)*inverse;
    const int64_t dlng=((neu_y_cm*0.01)*inverse)/scale(origin_lat+dlat/2);
    const int32_t absolute_cm=int32_t(neu_z_cm)+origin_alt;
    const float global_alt=absolute_cm*0.01f;
    std::printf("{\"log\":[%.17g,%.17g,%.17g],\"local\":[%.17g,%.17g,%.17g],\"global_target\":[%d,%lld,%.17g]}\n",
        double(float(lat)),double(float(lng)),double(float(alt_cm)),double(float(north)),double(float(east)),double(float(down)),
        origin_lat+dlat,static_cast<long long>(origin_lng+dlng),double(global_alt));
}
