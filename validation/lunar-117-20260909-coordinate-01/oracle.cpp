// Numerical harness: pinned PX4 BSD-3-Clause and ArduPilot GPL-3.0-or-later
// method bodies transcribed from sources identified in summary.md.
// Shim only supplies fields, scalar helpers, vectors and input/output plumbing.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <iomanip>
namespace math {
double radians(double x) { return x * (M_PI / 180.0); }
double constrain(double x, double lo, double hi) { return std::clamp(x, lo, hi); }
}
constexpr double CONSTANTS_RADIUS_OF_EARTH = 6371000.0;
struct MapProjection {
 double _ref_lat, _ref_lon, _ref_sin_lat, _ref_cos_lat;
 uint64_t _ref_timestamp; bool _ref_init_done;
 void initReference(double lat_0, double lon_0, uint64_t timestamp);
 void project(double lat, double lon, float &x, float &y) const;
};
void MapProjection::initReference(double lat_0, double lon_0, uint64_t timestamp)
{
 _ref_timestamp = timestamp;
 _ref_lat = math::radians(lat_0);
 _ref_lon = math::radians(lon_0);
 _ref_sin_lat = sin(_ref_lat);
 _ref_cos_lat = cos(_ref_lat);
 _ref_init_done = true;
}
void MapProjection::project(double lat, double lon, float &x, float &y) const
{
 const double lat_rad = math::radians(lat);
 const double lon_rad = math::radians(lon);
 const double sin_lat = sin(lat_rad);
 const double cos_lat = cos(lat_rad);
 const double cos_d_lon = cos(lon_rad - _ref_lon);
 const double arg = math::constrain(_ref_sin_lat * sin_lat + _ref_cos_lat * cos_lat * cos_d_lon, -1.0, 1.0);
 const double c = acos(arg);
 double k = 1.0;
 if (fabs(c) > 0) { k = (c / sin(c)); }
 x = static_cast<float>(k * (_ref_cos_lat * sin_lat - _ref_sin_lat * cos_lat * cos_d_lon) * CONSTANTS_RADIUS_OF_EARTH);
 y = static_cast<float>(k * cos_lat * sin(lon_rad - _ref_lon) * CONSTANTS_RADIUS_OF_EARTH);
}
using ftype = float;
#define DEG_TO_RAD (M_PI / 180.0f)
#define cosF cosf
#define MAX(a,b) ((a)>(b)?(a):(b))
struct Vector3f { float x,y,z; Vector3f(float a,float b,float c):x(a),y(b),z(c){} };
struct Location {
 int32_t lat,lng,alt;
 static constexpr float LOCATION_SCALING_FACTOR = 0.011131884502145034;
 static ftype longitude_scale(int32_t lat);
 static int32_t diff_longitude(int32_t lon1,int32_t lon2);
 Vector3f get_distance_NED(const Location &loc2) const;
};
ftype Location::longitude_scale(int32_t lat)
{
 ftype scale = cosF(lat * (1.0e-7 * DEG_TO_RAD));
 return MAX(scale, 0.01);
}
int32_t Location::diff_longitude(int32_t lon1, int32_t lon2)
{
 if ((lon1 & 0x80000000) == (lon2 & 0x80000000)) { return lon1 - lon2; }
 int64_t dlon = int64_t(lon1)-int64_t(lon2);
 if (dlon > 1800000000LL) { dlon -= 3600000000LL; }
 else if (dlon < -1800000000LL) { dlon += 3600000000LL; }
 return int32_t(dlon);
}
Vector3f Location::get_distance_NED(const Location &loc2) const
{
 return Vector3f((loc2.lat - lat) * LOCATION_SCALING_FACTOR,
                 diff_longitude(loc2.lng,lng) * LOCATION_SCALING_FACTOR * longitude_scale((lat+loc2.lat)/2),
                 (alt - loc2.alt) * 0.01);
}
int main() {
 double lat,lon,tlat,tlon,ha,oa,h;
 std::cout << std::setprecision(17);
 while(std::cin>>lat>>lon>>tlat>>tlon>>ha>>oa>>h) {
  MapProjection p; p.initReference(lat,lon,1); float n,e; p.project(tlat,tlon,n,e);
  float z=oa-(ha+h), wire=h;
  int32_t la=tlat*1E7, lo=tlon*1E7, cm=double(wire)*100.0;
  Location a{int32_t(std::round(lat*1E7)),int32_t(std::round(lon*1E7)),int32_t(std::round(ha*100))};
  Location b{la,lo,a.alt+cm}; auto d=a.get_distance_NED(b);
  std::cout<<n<<' '<<e<<' '<<z<<' '<<la<<' '<<lo<<' '<<cm<<' '<<d.y<<' '<<d.x<<' '<<-d.z<<'\n';
 }
}
