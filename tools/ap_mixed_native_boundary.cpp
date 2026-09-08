// Dependency stubs only. Actual candidate functions are inserted in actual.inc.
// Location conversion, Guided/fence, math helpers and DDS layout are NOT real AP.
#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>
#include <iostream>
#include <cstdlib>
#include "constants.inc"
static int assertions=0;
#define CHECK(x) do { ++assertions; if (!(x)) { std::cerr << "FAIL line " << __LINE__ << ": " #x "\n"; std::exit(1); } } while (0)
struct Vector2f { float x=0,y=0; };
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
static bool altitude_conversion_ok=true, invalidate_on_set=false;
static float altitude_result=5;
static int altitude_conversions=0, altitude_sets=0;
struct Location {
    enum class AltFrame { ABSOLUTE=0, ABOVE_HOME=1, ABOVE_ORIGIN=2, ABOVE_TERRAIN=3 };
    int32_t lat=0,lng=0,alt=0; AltFrame frame=AltFrame::ABSOLUTE;
    bool valid=true;
    Location()=default;
    Location(int32_t a,int32_t b,int32_t c,AltFrame f):lat(a),lng(b),alt(c),frame(f){}
    bool get_vector_from_origin_NED_m(Vector3p& out) const {
        ++conversions;if(!conversion_ok) return false;out=origin_result;return true;
    }
    bool initialised() const { return valid; }
    void set_alt_cm(int32_t value, AltFrame f) { ++altitude_sets; alt=value; frame=f; if(invalidate_on_set) valid=false; }
    bool get_alt_m(AltFrame f, float& out) const;
};
static Location converted_location;
bool Location::get_alt_m(AltFrame f, float& out) const {
    CHECK(f==AltFrame::ABOVE_ORIGIN); ++altitude_conversions;
    converted_location=*this;if(!altitude_conversion_ok) return false;out=altitude_result;return true;
}
// Deliberately scripted Location output, not a reimplementation of real Location.
struct AHRS {
    bool location_ok=true, home_set=true, origin_ok=true;
    int locations=0, origins=0, homes=0;
    Location current{350001234,1390005678,12000,Location::AltFrame::ABSOLUTE};
    Location home{35,139,10000,Location::AltFrame::ABSOLUTE};
    Location origin{36,140,9800,Location::AltFrame::ABSOLUTE};
    bool get_location(Location& out) { ++locations;out=current;return location_ok; }
    bool home_is_set() { return home_set; }
    bool get_origin(Location& out) { ++origins;out=origin;return origin_ok; }
    const Location& get_home() { ++homes;return home; }
} ahrs_stub;
float radians(float x) { return x*float(M_PI/180.0); }
float wrap_PI(float x) { return std::remainder(x, float(2*M_PI)); }
static constexpr auto MAP_FRAME="map";
struct External {
    int calls=0, path=0; bool result=true, use_yaw=false;
    float yaw=0; Location loc; Vector3f vel;
    int32_t altitude_cm=0; Vector2f velocity_xy;
    virtual ~External()=default;
    bool save(int p,const Location& l,bool u,float y,Vector3f v={}) {
        ++calls;if(!result) return false;path=p;loc=l;use_yaw=u;yaw=y;vel=v;return true;
    }
    virtual bool set_global_position(const Location& l) { return save(1,l,false,0); }
    virtual bool set_global_position_and_yaw(const Location& l,float y) { return save(2,l,true,y); }
    virtual bool set_global_position_velocity_and_yaw(const Location& l,const Vector3f& v,bool u,float y) { return save(3,l,u,y,v); }
    virtual bool set_altitude_velocity_xy_and_yaw(int32_t alt,const Vector2f& v,float y) {
        ++calls;if(!result) return false;path=4;altitude_cm=alt;velocity_xy=v;yaw=y;use_yaw=true;return true;
    }
};
static External* endpoint=nullptr;
namespace AP { External* externalcontrol() { return endpoint; } AHRS& ahrs(){return ahrs_stub;} }
struct AP_DDS_External_Control {
    bool handle_global_position_control(ardupilot_msgs_msg_GlobalPosition&);
    bool convert_alt_frame(uint8_t,Location::AltFrame&);
};
struct Guided {
    int calls=0; bool result=true,use_yaw=false,rate=false,relative=false;
    float yaw=0,yaw_rate=0; Vector3p pos;Vector3f vel;
    int mixed_calls=0; float down=0; Vector2f velocity_xy;
    bool set_pos_vel_NED_m(Vector3p p,Vector3f v,bool u,float y,bool r,float yr,bool rel) {
        ++calls;pos=p;vel=v;use_yaw=u;yaw=y;rate=r;yaw_rate=yr;relative=rel;return result;
    }
    bool set_vel_NE_pos_D_m(const Vector2f& v,float d,float y) {
        ++mixed_calls;if(!result) return false;velocity_xy=v;down=d;yaw=y;return true;
    }
};
struct FlightMode { bool guided=true; bool in_guided_mode(){return guided;} };
struct Motors { bool is_armed=true; bool armed(){return is_armed;} };
struct { Guided mode_guided; FlightMode flight; Motors motor;
    FlightMode* flightmode=&flight; Motors* motors=&motor; } copter;
struct AP_ExternalControl_Copter: External {
    bool ready_for_external_control();
    bool set_global_position_velocity_and_yaw(const Location&,const Vector3f&,bool,float) override;
    bool set_altitude_velocity_xy_and_yaw(int32_t,const Vector2f&,float) override;
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
        CHECK(spy.loc.frame==(frame==5?Location::AltFrame::ABSOLUTE:frame==6?Location::AltFrame::ABOVE_HOME:Location::AltFrame::ABOVE_TERRAIN));
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
    endpoint=&spy;spy.result=true;
    auto mixed=[]() { Message out;out.coordinate_frame=6;out.type_mask=2531;out.altitude=3.125f;out.velocity.linear={1.25,-2.5,0};out.yaw=0.25f;return out; };
    accepted=0;
    for(unsigned mask=0;mask<65536;++mask) {
        Message msg=mixed();msg.type_mask=mask;n=spy.calls;
        bool expected=mask==2496 || mask==2552 || mask==3520 || mask==3576 || mask==2531;
        CHECK(dds.handle_global_position_control(msg)==expected);CHECK(spy.calls==n+int(expected));
        accepted+=expected;if(mask==2531) CHECK(spy.path==4);
    }
    CHECK(accepted==5);
    for(int frame=0;frame<256;++frame) {
        Message msg=mixed();msg.coordinate_frame=frame;
        if(frame==6) CHECK(dds.handle_global_position_control(msg));else reject(msg);
    }
    for(auto name:{"", "odom", "base_link", "MAP", "map "}) {Message msg=mixed();msg.header.frame_id=name;reject(msg);}
    auto check_mixed_target=[&](const Message& msg) {
        CHECK(spy.path==4 && spy.altitude_cm==int32_t(double(msg.altitude)*100));
        CHECK(spy.velocity_xy.x==float(msg.velocity.linear.y) && spy.velocity_xy.y==float(msg.velocity.linear.x));
        CHECK(std::fabs(std::sin(spy.yaw)-std::cos(msg.yaw))<1e-6);
        CHECK(std::fabs(std::cos(spy.yaw)-std::sin(msg.yaw))<1e-6);
    };
    // Every inactive scalar independently, then all together: the exact mask selects axes.
    for(auto value:{nan,inf,-inf,1.e300,-1.e300,17.0}) {
        for(int field=0;field<12;++field) {
            Message msg=mixed();
            double* inactive[]={&msg.latitude,&msg.longitude,&msg.velocity.linear.z,
                &msg.velocity.angular.x,&msg.velocity.angular.y,&msg.velocity.angular.z,
                &msg.acceleration_or_force.linear.x,&msg.acceleration_or_force.linear.y,&msg.acceleration_or_force.linear.z,
                &msg.acceleration_or_force.angular.x,&msg.acceleration_or_force.angular.y,&msg.acceleration_or_force.angular.z};
            *inactive[field]=value;CHECK(dds.handle_global_position_control(msg));check_mixed_target(msg);
        }
        Message msg=mixed();msg.latitude=msg.longitude=value;msg.velocity.linear.z=value;
        msg.velocity.angular={value,value,value};msg.acceleration_or_force={{value,value,value},{value,value,value}};
        CHECK(dds.handle_global_position_control(msg));check_mixed_target(msg);
    }
    for(auto value:{nan,inf,-inf}) for(int field=0;field<4;++field) {
        Message msg=mixed();
        if(field==0)msg.altitude=value;else if(field==1)msg.yaw=value;
        else if(field==2)msg.velocity.linear.x=value;else msg.velocity.linear.y=value;
        reject(msg);
    }
    const double limit=std::sqrt(double(std::numeric_limits<float>::max())/4.0)/100.0;
    for(int axis=0;axis<2;++axis) for(auto sign:{-1.0,1.0}) {
        for(auto value:{limit,std::nextafter(limit,0.0)}) {
            Message msg=mixed();(axis==0?msg.velocity.linear.x:msg.velocity.linear.y)=sign*value;
            CHECK(dds.handle_global_position_control(msg));
        }
        for(auto value:{std::nextafter(limit,inf),limit*1.001,double(std::numeric_limits<float>::max()),double(std::numeric_limits<float>::max())*2}) {
            Message msg=mixed();(axis==0?msg.velocity.linear.x:msg.velocity.linear.y)=sign*value;reject(msg);
        }
    }
    for(auto sign:{-1.0,1.0}) {
        Message msg=mixed();msg.velocity.linear={sign*limit,sign*limit,0};CHECK(dds.handle_global_position_control(msg));
        float x_cm=spy.velocity_xy.x*100.f,y_cm=spy.velocity_xy.y*100.f;
        CHECK(std::isfinite(x_cm*x_cm+y_cm*y_cm));
    }
    for(auto value:{21474836.f,-21474836.f,3.125f,-3.125f,0.f}) {
        Message msg=mixed();msg.altitude=value;CHECK(dds.handle_global_position_control(msg));check_mixed_target(msg);
    }
    for(auto value:{21474838.f,-21474838.f,std::numeric_limits<float>::max(),-std::numeric_limits<float>::max()}) {
        Message msg=mixed();msg.altitude=value;reject(msg);
    }
    for(auto yaw:{0.f,float(M_PI/2),float(M_PI),-float(M_PI/2),7.f,-7.f}) {
        Message msg=mixed();msg.yaw=yaw;CHECK(dds.handle_global_position_control(msg));check_mixed_target(msg);
    }
    Message msg=mixed();CHECK(dds.handle_global_position_control(msg));
    const float saved_yaw=spy.yaw;const int32_t saved_alt=spy.altitude_cm;const Vector2f saved_v=spy.velocity_xy;
    spy.result=false;n=spy.calls;msg.altitude=17;
    CHECK(!dds.handle_global_position_control(msg));CHECK(spy.calls==n+1);
    CHECK(spy.yaw==saved_yaw && spy.altitude_cm==saved_alt && spy.velocity_xy.x==saved_v.x && spy.velocity_xy.y==saved_v.y);
    endpoint=nullptr;n=spy.calls;CHECK(!dds.handle_global_position_control(msg));CHECK(spy.calls==n);
    // The spy's refusal is scripted. No assertion here claims true controller atomicity.
    endpoint=&adapter;copter.mode_guided.result=true;
    auto helper_reject=[&](int32_t alt=300,Vector2f v={2,1},float yaw=0) {
        int before=copter.mode_guided.mixed_calls;float d=copter.mode_guided.down,y=copter.mode_guided.yaw;
        Vector2f old=copter.mode_guided.velocity_xy;
        CHECK(!adapter.set_altitude_velocity_xy_and_yaw(alt,v,yaw));CHECK(copter.mode_guided.mixed_calls==before);
        CHECK(copter.mode_guided.down==d && copter.mode_guided.yaw==y && copter.mode_guided.velocity_xy.x==old.x && copter.mode_guided.velocity_xy.y==old.y);
    };
    CHECK(adapter.set_altitude_velocity_xy_and_yaw(300,{2,1},0.75));
    CHECK(copter.mode_guided.down==-5 && copter.mode_guided.velocity_xy.x==2 && copter.mode_guided.velocity_xy.y==1 && copter.mode_guided.yaw==0.75);
    CHECK(converted_location.lat==ahrs_stub.current.lat && converted_location.lng==ahrs_stub.current.lng);
    CHECK(converted_location.alt==300 && converted_location.frame==Location::AltFrame::ABOVE_HOME);
    c=conversions;msg=mixed();CHECK(dds.handle_global_position_control(msg));CHECK(conversions==c);
    int locations=ahrs_stub.locations;
    copter.flight.guided=false;helper_reject();copter.flight.guided=true;
    copter.motor.is_armed=false;helper_reject();copter.motor.is_armed=true;
    for(auto value:{float(nan),float(inf),-float(inf)}) {
        helper_reject(300,{value,1});helper_reject(300,{1,value});helper_reject(300,{1,2},value);
    }
    CHECK(ahrs_stub.locations==locations);
    c=altitude_conversions;
    ahrs_stub.location_ok=false;helper_reject();ahrs_stub.location_ok=true;
    ahrs_stub.current.valid=false;helper_reject();ahrs_stub.current.valid=true;
    ahrs_stub.home_set=false;helper_reject();ahrs_stub.home_set=true;
    ahrs_stub.origin_ok=false;helper_reject();ahrs_stub.origin_ok=true;
    CHECK(altitude_conversions==c);
    const int32_t imin=std::numeric_limits<int32_t>::min(),imax=std::numeric_limits<int32_t>::max();
    // Both positive/negative absolute and origin-relative int32 intermediate overflow.
    ahrs_stub.home.alt=1;ahrs_stub.origin.alt=0;helper_reject(imax);
    ahrs_stub.home.alt=-1;helper_reject(imin);
    ahrs_stub.home.alt=0;ahrs_stub.origin.alt=-1;helper_reject(imax);
    ahrs_stub.origin.alt=1;helper_reject(imin);
    CHECK(altitude_conversions==c);
    ahrs_stub.home.alt=0;ahrs_stub.origin.alt=0;
    CHECK(adapter.set_altitude_velocity_xy_and_yaw(imin,{2,1},0));
    CHECK(adapter.set_altitude_velocity_xy_and_yaw(imax,{2,1},0));
    ahrs_stub.home.alt=10000;ahrs_stub.origin.alt=9800;
    invalidate_on_set=true;c=altitude_conversions;helper_reject();CHECK(altitude_conversions==c);invalidate_on_set=false;
    altitude_conversion_ok=false;helper_reject();altitude_conversion_ok=true;
    for(auto value:{float(nan),float(inf),-float(inf)}) {altitude_result=value;helper_reject();}
    altitude_result=5;CHECK(adapter.set_altitude_velocity_xy_and_yaw(300,{2,1},0.5));
    n=copter.mode_guided.mixed_calls;float old_down=copter.mode_guided.down,old_yaw=copter.mode_guided.yaw;
    copter.mode_guided.result=false;
    CHECK(!adapter.set_altitude_velocity_xy_and_yaw(400,{9,8},1));CHECK(copter.mode_guided.mixed_calls==n+1);
    CHECK(copter.mode_guided.down==old_down && copter.mode_guided.yaw==old_yaw);
    n=copter.mode_guided.mixed_calls;msg=mixed();CHECK(!dds.handle_global_position_control(msg));CHECK(copter.mode_guided.mixed_calls==n+1);
    std::cout << "PASS: " << assertions << " assertions; 131072 exhaustive mask cases (65536 each frame 5/6); old P/PV regression and new mixed boundary; exact DDS/helper bodies; explicit dependency stubs only, not controller/fence/Location/reset/timeout/flight proof\n";
}
