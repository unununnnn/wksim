// Dependency stubs only. Actual candidate functions are inserted in actual.inc.
// Location conversion, Guided/fence, math helpers and DDS layout are NOT real AP.
#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>
#include <iostream>
#include <cstdlib>
#include "constants.inc"
#define CHECK(x) do { if (!(x)) { std::cerr << "FAIL line " << __LINE__ << ": " #x "\n"; std::exit(1); } } while (0)
struct Vector3f { float x=0,y=0,z=0; };
using Vector3p = Vector3f;
struct Triple { double x=0,y=0,z=0; };
struct Twist { Triple linear, angular; };
struct ardupilot_msgs_msg_GlobalPosition {
    struct { const char* frame_id="map"; } header;
    uint8_t coordinate_frame=5;
    uint16_t type_mask=2496;
    double latitude=35, longitude=139;
    float altitude=100;
    Twist velocity{{1,2,3},{}}, acceleration_or_force;
    float yaw=0;
};
static int conversions=0;
static bool conversion_ok=true;
static Vector3p origin_result{10,20,-30};
struct Location {
    enum class AltFrame { ABSOLUTE, ABOVE_HOME, ABOVE_TERRAIN };
    int32_t lat=0,lng=0,alt=0; AltFrame frame=AltFrame::ABSOLUTE;
    Location()=default;
    Location(int32_t a,int32_t b,int32_t c,AltFrame f):lat(a),lng(b),alt(c),frame(f){}
    bool get_vector_from_origin_NED_m(Vector3p& out) const {
        ++conversions; out=origin_result; return conversion_ok;
    }
};
float radians(float x) { return x*float(M_PI/180.0); }
float wrap_PI(float x) { return std::remainder(x, float(2*M_PI)); }
static constexpr auto MAP_FRAME="map";
struct External {
    int calls=0, path=0; bool result=true, use_yaw=false;
    float yaw=0; Location loc; Vector3f vel;
    virtual ~External()=default;
    bool save(int p,const Location& l,bool u,float y,Vector3f v={}) {
        ++calls;path=p;loc=l;use_yaw=u;yaw=y;vel=v;return result;
    }
    virtual bool set_global_position(const Location& l) { return save(1,l,false,0); }
    virtual bool set_global_position_and_yaw(const Location& l,float y) { return save(2,l,true,y); }
    virtual bool set_global_position_velocity_and_yaw(const Location& l,const Vector3f& v,bool u,float y) { return save(3,l,u,y,v); }
};
static External* endpoint=nullptr;
namespace AP { External* externalcontrol() { return endpoint; } }
struct AP_DDS_External_Control {
    bool handle_global_position_control(ardupilot_msgs_msg_GlobalPosition&);
    bool convert_alt_frame(uint8_t,Location::AltFrame&);
};
struct Guided {
    int calls=0; bool result=true,use_yaw=false,rate=false,relative=false;
    float yaw=0,yaw_rate=0; Vector3p pos;Vector3f vel;
    bool set_pos_vel_NED_m(Vector3p p,Vector3f v,bool u,float y,bool r,float yr,bool rel) {
        ++calls;pos=p;vel=v;use_yaw=u;yaw=y;rate=r;yaw_rate=yr;relative=rel;return result;
    }
};
struct FlightMode { bool guided=true; bool in_guided_mode(){return guided;} };
struct Motors { bool is_armed=true; bool armed(){return is_armed;} };
struct { Guided mode_guided; FlightMode flight; Motors motor;
    FlightMode* flightmode=&flight; Motors* motors=&motor; } copter;
struct AP_ExternalControl_Copter: External {
    bool ready_for_external_control();
    bool set_global_position_velocity_and_yaw(const Location&,const Vector3f&,bool,float) override;
};
#include "actual.inc"
bool same(Vector3f a,Vector3f b) { return a.x==b.x && a.y==b.y && a.z==b.z; }
int main() {
    AP_DDS_External_Control dds; External spy; endpoint=&spy;
    using Message=ardupilot_msgs_msg_GlobalPosition;
    auto reject=[&](Message m) { int n=spy.calls; CHECK(!dds.handle_global_position_control(m)); CHECK(spy.calls==n); };
    int accepted=0;
    for (unsigned mask=0;mask<65536;++mask) {
        Message m; m.type_mask=mask; int n=spy.calls;
        bool expected=mask==2496 || mask==2552 || mask==3520 || mask==3576;
        CHECK(dds.handle_global_position_control(m)==expected);
        CHECK(spy.calls==n+int(expected)); accepted+=expected;
        if(expected) { CHECK(spy.path==((mask&56)?((mask&1024)?1:2):3)); }
    }
    CHECK(accepted==4);
    for(auto mask:{2496,2552,3520,3576}) for(auto frame:{5,6,11}) {
        Message m; m.type_mask=mask;m.coordinate_frame=frame;
        CHECK(dds.handle_global_position_control(m));
        CHECK(spy.loc.lat==350000000 && spy.loc.lng==1390000000 && spy.loc.alt==10000);
        CHECK(int(spy.loc.frame)==(frame==5?0:frame==6?1:2));
        CHECK(spy.use_yaw==!(mask&1024));
        CHECK(std::fabs(spy.yaw-((mask&1024)?0:float(M_PI/2)))<1e-6);
        if(!(mask&56)) CHECK(same(spy.vel,{2,1,-3}));
    }
    for(int frame=0;frame<256;++frame) if(frame!=5 && frame!=6 && frame!=11) {
        Message m;m.coordinate_frame=frame;reject(m);
    }
    for(auto name:{"", "odom", "base_link", "MAP", "map "}) {Message m;m.header.frame_id=name;reject(m);}
    double nan=std::numeric_limits<double>::quiet_NaN(), inf=std::numeric_limits<double>::infinity();
    for(auto mask:{2496,2552,3520,3576}) for(auto value:{nan,inf,-inf}) {
        Message m;m.type_mask=mask;m.latitude=value;reject(m);
        m=Message{};m.type_mask=mask;m.longitude=value;reject(m);
        m=Message{};m.type_mask=mask;m.altitude=value;reject(m);
        m=Message{};m.type_mask=mask;m.yaw=value;
        if(mask&1024) CHECK(dds.handle_global_position_control(m)); else reject(m);
    }
    for(auto value:{90.0001,-90.0001}) {Message m;m.latitude=value;reject(m);}
    for(auto value:{180.0001,-180.0001}) {Message m;m.longitude=value;reject(m);}
    for(auto value:{21474836.f,-21474836.f}) {Message m;m.altitude=value;reject(m);}
    for(int axis=0;axis<3;++axis) for(auto value:{nan,inf,-inf, double(std::numeric_limits<float>::max())*2,-double(std::numeric_limits<float>::max())*2}) {
        for(auto mask:{2496,3520,2552,3576}) {
            Message m;m.type_mask=mask;
            (axis==0?m.velocity.linear.x:axis==1?m.velocity.linear.y:m.velocity.linear.z)=value;
            if(mask&56) CHECK(dds.handle_global_position_control(m)); else reject(m);
        }
    }
    for(auto value:{double(std::numeric_limits<float>::max()),-double(std::numeric_limits<float>::max())}) {
        Message m;m.velocity.linear={value,value,value};CHECK(dds.handle_global_position_control(m));
    }
    for(auto yaw:{0.f,float(M_PI/2),float(M_PI),-float(M_PI/2)}) {
        Message m;m.yaw=yaw;CHECK(dds.handle_global_position_control(m));
        CHECK(std::fabs(std::sin(spy.yaw)-std::cos(yaw))<1e-6);
        CHECK(std::fabs(std::cos(spy.yaw)-std::sin(yaw))<1e-6);
    }
    for(auto mask:{2496,2552,3520,3576}) {
        Message m;m.type_mask=mask;spy.result=false;int n=spy.calls;
        CHECK(!dds.handle_global_position_control(m));CHECK(spy.calls==n+1);
        endpoint=nullptr;n=spy.calls;CHECK(!dds.handle_global_position_control(m));CHECK(spy.calls==n);endpoint=&spy;
    }
    AP_ExternalControl_Copter adapter;endpoint=&adapter;Message m;
    CHECK(dds.handle_global_position_control(m));CHECK(copter.mode_guided.calls==1);
    CHECK(same(copter.mode_guided.pos,origin_result));CHECK(same(copter.mode_guided.vel,{2,1,-3}));
    CHECK(copter.mode_guided.use_yaw && !copter.mode_guided.rate && !copter.mode_guided.relative && copter.mode_guided.yaw_rate==0);
    auto adapter_reject=[&](Vector3f v={1,2,3},bool u=true,float y=0) {
        int n=copter.mode_guided.calls;CHECK(!adapter.set_global_position_velocity_and_yaw({},v,u,y));CHECK(copter.mode_guided.calls==n);
    };
    copter.flight.guided=false;int c=conversions;adapter_reject();CHECK(conversions==c);copter.flight.guided=true;
    copter.motor.is_armed=false;adapter_reject();CHECK(conversions==c);copter.motor.is_armed=true;
    for(int axis=0;axis<3;++axis) for(auto value:{float(nan),float(inf),-float(inf)}) {
        Vector3f v{1,2,3};(axis==0?v.x:axis==1?v.y:v.z)=value;adapter_reject(v);CHECK(conversions==c);
    }
    adapter_reject({1,2,3},true,float(nan));CHECK(conversions==c);
    conversion_ok=false;adapter_reject();conversion_ok=true;
    for(int axis=0;axis<3;++axis) for(auto value:{float(nan),float(inf),-float(inf)}) {
        origin_result={10,20,-30};(axis==0?origin_result.x:axis==1?origin_result.y:origin_result.z)=value;adapter_reject();
    }
    origin_result={10,20,-30};
    CHECK(adapter.set_global_position_velocity_and_yaw({}, {4,5,6},false,float(nan)));
    CHECK(!copter.mode_guided.use_yaw && copter.mode_guided.yaw==0 && same(copter.mode_guided.vel,{4,5,6}));
    copter.mode_guided.result=false;int n=copter.mode_guided.calls;
    CHECK(!dds.handle_global_position_control(m));CHECK(copter.mode_guided.calls==n+1);
    std::cout << "PASS: actual DDS/adapter slices; 65536 masks, frames, finite/range checks, ENU/NED, yaw, null endpoint, readiness, conversion and Guided return forwarding; stubs only, not SITL\n";
}
