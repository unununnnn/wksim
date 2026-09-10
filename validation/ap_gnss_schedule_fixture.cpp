// Logical header boundaries only; real AP evidence is a separate probe.
#include "SIM_WksimGNSS.h"
#include <string>
struct Data {
    unsigned timestamp_ms=100, num_sats=10;
    double latitude=40,longitude=116,altitude=50,speedN=0,speedE=0,speedD=0;
    double yaw_deg=0,roll_deg=0,pitch_deg=0,horizontal_acc=1,vertical_acc=1,speed_acc=0;
    bool have_lock=true;
};
int main(int argc,char**argv) {
    if(argc!=2)return 2;
    std::string mode=argv[1];auto &c=WksimGNSS::context();
    if(mode=="long_tick" || mode=="overrun") {
        c.tick=mode=="long_tick"?179999:180000;
        char raw[256];snprintf(raw,sizeof(raw),"{\"wksim\":\"%s:%s:1:%llu\",\"timestamp\":180.0}",getenv("WKSIM_RUN"),getenv("WKSIM_EPOCH"),c.tick+1);
        WksimGNSS::receive(raw);return c.tick==180000?0:1;
    }
    c.tick=100;
    if(mode=="late") {WksimGNSS::plan("\"gnss_plan\":\"1099:16099\",\"timestamp\":0.1}");return 1;}
    if(mode=="noncanonical") {WksimGNSS::plan("\"gnss_plan\":\"02000:17000\",\"timestamp\":0.1}");return 1;}
    WksimGNSS::plan("\"gnss_plan\":\"2000:17000\",\"timestamp\":0.1}");
    if(mode=="changed") {WksimGNSS::plan("\"gnss_plan\":\"2001:17001\",\"timestamp\":0.1}");return 1;}
    if(mode=="missing") {WksimGNSS::plan("\"timestamp\":0.1}");return 1;}
    if(mode=="bounds") {
        c.fresh[0]=true;c.tick=1999;if(WksimGNSS::suppress(0))return 1;
        c.tick=2000;if(!WksimGNSS::suppress(0))return 1;
        c.tick=16999;if(!WksimGNSS::suppress(0))return 1;
        c.tick=17000;if(WksimGNSS::suppress(0))return 1;
        return 0;
    }
    c.tick=mode=="late_recreate"?47001:18001;
    WksimGNSS::sensor_created(0);
    Data d;
    if(mode=="old_generation") {c.tick=18200;d.timestamp_ms=18000;WksimGNSS::sample(0,d,18199000);return 1;}
    c.tick=18200;d.timestamp_ms=0;
    if(WksimGNSS::sample(0,d,18199000))return 1;
    c.tick=18400;d.timestamp_ms=18200;
    return WksimGNSS::sample(0,d,18399000) && c.generation[0]==1?0:1;
}
