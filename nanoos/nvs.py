'''TODO
- Implement haversine formula.
- Implement direction with distance.
- Fine tune check_asset_data_age to represent days, hours, minutes, seconds.
- Format get_recent_data output to be more intuitive.
'''

from datetime import datetime,timedelta, timezone
from pyproj import Proj
import pytz
import requests

class NVS():
    def __init__(self):
        self.base = 'http://nvs.nanoos.org/services/get_asset_info.php'
        self.payload = {}
        self.ISO8601 = '%Y-%m-%dT%H:%M:%SZ'
    
    def status(self):
        '''Ping on NVS services.
        @return -- If the response code is OK (200), return True. 
            Otherwise, return False.
        '''
        response = requests.get(self.base)
        if response.status_code == requests.codes.ok:
            return True
        else:
            return False  
    
    def get_all_assets_metadata(self,online=False):
        '''Get the metadata for all NVS assets.
        @param online -- only get the metadata for active assets if True.
        @return -- a list of asset metadata represented in dicts      
        '''
        self.payload['opt'] = 'meta'
        content = requests.get(self.base,params=self.payload).json()
        if content['success'] is True:
            assets = content['result']
            if online is True:
                for asset in assets:
                    if "offline" in asset['deploy_status']:
                        assets.remove(asset)
            return assets
    
    def _set_projection(self):
        '''Set the projection for UTM conversion.
        @param lon -- the longitude of the ship in decimal degrees. 
        Note: The longitude is used to determine the UTM zone. This was coded
        to only consider assets that exist within NVS. This will need to be
        updated if assets exist outside of UTM zones 8-10.
        '''
        if self.ship_lon >= -126:
            zone = 10
        elif -129 < self.ship_lon < -126:
            zone = 9
        elif self.ship_lon <= -129:
            zone = 8
        self.projection = Proj(proj='utm',zone=zone,ellps='WGS84')
    
    def _is_in_range(self,asset_lat,asset_lon,radius):
        '''Deterimine if an asset is in range of the ship lat/lon using
        the equation of a circle on UTM values.
        @param asset_lat -- the latitude of the asset in decimal degrees.
        @param asset_lon -- the longitude of the asset in decimal degrees.
        @param -- the distance from the ship to consider as "nearby".
        @return -- True if the asset is in the radius, False if not.
        '''
        ship_x,ship_y = self.projection(self.ship_lon,self.ship_lat)        
        asset_x,asset_y = self.projection(asset_lon,asset_lat)
        left = (asset_x-ship_x)**2 + (asset_y-ship_y)**2 #(x-h)^2 + (y-k)^2
        right = radius**2 #r^2
        if left <= right: # If (x-h)^2 + (y-k)^2 <= r^2
            return True
        else:
            return False
    
    def get_nearby_assets_metadata(self,ship_lat,ship_lon,
                          radius=5000,online=False):
        '''Get a list of assets that are near the ship.
        @param ship_lat -- the ship latitude in decimal degrees.
        @param ship_lon -- the ship longitude in decimal degrees.
        @param radius -- the distance in meters to look for nearby assets.
        @online -- if set to True, only considers assets that are "online".
        @return -- a list of assets within x meters of the ship.
        '''
        self.ship_lat = ship_lat
        self.ship_lon = ship_lon
        self._set_projection()        
        assets = self.get_all_assets_metadata(online=online)
        nearby = []
        for asset in assets:
            asset_lat = asset['lat']
            asset_lon = asset['lon']
            if self._is_in_range(asset_lat,asset_lon,radius):
                nearby.append(asset)
        return nearby

    def get_distance_from_ship(self,ship_lat,ship_lon,asset_lat,asset_lon):
        '''Compute the Euclidian distance in meters between the ship 
        and an asset.
        @param ship_lat -- the latitude of the ship in decimal degrees.
        @param ship_lon -- the longitude of the ship in decimal degrees.
        @param asset_lat -- the latitude of the asset in decimal degrees.
        @param asset_lon -- the longitude of the asset in decimal degrees.
        @return -- the Euclidian distance between the two points in meters.
            Rounded according to Python's int functionality.
        '''
        self.ship_lat = ship_lat
        self.ship_lon = ship_lon
        self._set_projection()         
        ship_x,ship_y = self.projection(ship_lon,ship_lat)        
        asset_x,asset_y = self.projection(asset_lon,asset_lat)      
        distance = ((ship_lat - asset_lat)**2 + (ship_lon - asset_lon)**2)**0.5
        distance = int(distance*100000)
        return distance
    
    def check_asset_data_age(self,asset):
        '''Get the asset data age.
        @param asset -- a dict that must contain the asset's siso_id.
        @return -- a timedelta object, returned as X days, HH:MM:SS.
        
        NOTE: This assumes that assets within NVS all have US/Pacific
        timestamps. The asset and now times are made timezone aware, which
        allows math to be performed.
        '''
        self.payload['opt'] = 'data_age'
        self.payload['asset_id'] = asset['siso_id']
        content = requests.get(self.base,params=self.payload).json()
        if content['success'] is True:
            asset = content['result'].pop()     
            asset_time = datetime.fromtimestamp(asset['time'])  
            asset_time = asset_time.replace(tzinfo=pytz.timezone('US/Pacific'))
            now_time = datetime.now(timezone.utc)
            total = (now_time-asset_time).total_seconds()   
            age = timedelta(seconds = total)
            return age
            
    def get_recent_data(self,asset):
        '''Get the most recent data from the asset.
        @param asset -- a dict that must contain the asset's siso_id,
            measurements, and var_id's.
        @return -- a list/dict of each measurement by depth. Each element is
            renamed to be the var_id in combination with the depth. 
            That combo is then connected to a list in the order of 
            [value, units, time, depth]
            
            Example: 'H1_Salinity_-0.9 m': [10.9, 'PSU', 1613754000, -0.9]
            
        NOTE: Depth is in meters.    
        ''' 
        self.payload['opt'] = 'recent_values'
        self.payload['asset_id'] = asset['siso_id']
        self.payload['units_mode'] = 'v1'        
        all_data = []
        for var in asset['measurements']:
            self.payload['var_id'] = var['var_id']
            content = requests.get(self.base,params = self.payload).json()
            if content['success'] is True:
                samples = content['result']
                data = {}
                for sample in samples:
                    depth = float(sample['depth'].replace('m',''))
                    dt = datetime.fromtimestamp(sample['time'])
                    pacific = dt.replace(tzinfo=pytz.timezone('US/Pacific'))
                    utc = pacific.astimezone(timezone.utc)
                    time_str = utc.strftime(self.ISO8601)
                    d = [sample['value'],sample['units'],time_str,depth]
                    var_name = sample['var_id']+ '_' +sample['depth']
                    data[var_name] = d
            all_data.append(data)
        return all_data