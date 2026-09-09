
#pragma once
#include <string>
#include <unordered_map>
namespace ros {
struct NodeHandle {
    std::unordered_map<std::string, double> values;
    template<class T> void param(const std::string &name, T &out, T fallback) {
        const auto found = values.find(name);
        out = found == values.end() ? fallback : static_cast<T>(found->second);
    }
};
}
