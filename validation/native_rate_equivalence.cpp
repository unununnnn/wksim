// SPDX-License-Identifier: Apache-2.0
// Compile against the real fixed PX4 RateControl implementation, not a mock.
#include <lib/rate_control/rate_control.hpp>
#include "wksim_rate_adapter.hpp"
#include <cmath>
#include <cstring>
#include <iostream>

int main() {
    RateControl original, adapted;
    for (RateControl *pid : {&original, &adapted}) {
        pid->setPidGains({.15f,.15f,.2f},{.2f,.2f,.1f},{.003f,.003f,0.f});
        pid->setIntegratorLimit({.3f,.3f,.3f});
        pid->setFeedForwardGain({0.f,0.f,0.f});
    }
    WksimRateAdapter adapter;
    if (!adapter.valid()) { return 2; }
    uint64_t sample=0;
    for (unsigned i=0; i<20000; ++i) {
        const bool landed=i%89<7, armed=i%113>=5;
        if (!armed) { original.resetIntegral(); adapted.resetIntegral(); }
        matrix::Vector3<bool> positive{i%13==0,i%17==0,i%19==0};
        matrix::Vector3<bool> negative{i%23==0,i%29==0,i%31==0};
        original.setSaturationStatus(positive,negative);
        adapted.setSaturationStatus(positive,negative);
        matrix::Vector3f rates{},target{},acceleration{};
        for (unsigned axis=0; axis<3; ++axis) {
            rates(axis)=float(std::sin(double(i)*.017+double(axis)));
            target(axis)=float(std::cos(double(i)*.011+double(axis)));
            acceleration(axis)=float(3.*std::sin(double(i)*.023-double(axis)));
        }
        const float dt=i%3==0?.002f:i%3==1?.004f:.01f;
        sample+=uint64_t(double(dt)*1000000.);
        const auto expected=original.update(rates,target,acceleration,dt,landed);
        const auto actual=adapter.update(adapted,rates,target,acceleration,dt,landed,armed,sample);
        float a[3],b[3]; expected.copyTo(a);actual.copyTo(b);
        if (std::memcmp(a,b,sizeof(a))!=0) { std::cerr << "mismatch at " << i << '\n';return 1; }
        adapter.record_applied(actual,{0.f,0.f,-.53f});
    }
    std::cout << "20000 cycles / 60000 scalar outputs bit-identical\n";
}
