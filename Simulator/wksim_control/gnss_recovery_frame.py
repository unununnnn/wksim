"""Keep the original local waypoint datum across an observed AP home change."""
import math


def local_after_home_change(point,initial,current):
    for home in (initial,current):
        if set(home)!={'latitude_e7','longitude_e7','altitude_cm'} or any(type(v) is not int for v in home.values()):
            raise ValueError('Incomplete native home identity')
        if abs(home['latitude_e7'])>850000000 or abs(home['longitude_e7'])>1800000000:
            raise ValueError('Home outside local projection domain')
    if len(point)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) for v in point):
        raise ValueError('Invalid world point')
    north=(current['latitude_e7']-initial['latitude_e7'])*.011131884502145034
    longitude=((current['longitude_e7']-initial['longitude_e7']+1800000000)%3600000000)-1800000000
    east=longitude*.011131884502145034*math.cos(math.radians((current['latitude_e7']+initial['latitude_e7'])/2e7))
    up=(current['altitude_cm']-initial['altitude_cm'])/100.
    result=[point[0]-east,point[1]-north,point[2]-up]
    if max(abs(v) for v in (*result,east,north,up))>100:raise ValueError('Home shift exceeds local mission domain')
    return result
