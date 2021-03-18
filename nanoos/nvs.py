'''TODO
- Implement numpy for faster array calculations.
- Fine tune check_asset_data_age to represent days, hours, minutes, seconds.
- Format get_recent_data output to be more intuitive.
'''

from datetime import datetime,timedelta,timezone
import math
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
        '''Set the projection for UTM conversion.'''
        if self.ship_lon >= -126:
            zone = 10
        elif -129 < self.ship_lon < -126:
            zone = 9
        elif self.ship_lon <= -129:
            zone = 8
        self.projection = Proj(proj='utm',zone=zone,ellps='WGS84')
     
    
    def _get_haversine_distance(self):
        '''Compute the Great Circle distance between the ship and an asset.'''
        R = 6371e3
        phi_ship = self.ship_lat * math.pi/180
        phi_asset = self.asset_lat * math.pi/180
        delta_phi = (self.asset_lat - self.ship_lat) * math.pi/180
        delta_lambda = (self.asset_lon - self.ship_lon) * math.pi/180
        a = (math.sin(delta_phi/2) * math.sin(delta_phi/2) + math.cos(phi_ship) 
        * math.cos(phi_asset) * math.sin(delta_lambda/2) 
        * math.sin(delta_lambda/2))
        c = 2 * math.atan2(math.sqrt(a),math.sqrt(1-a))
        self.haversine = R *c
        
    def _get_manhattan_distance(self):
        '''Compute the manhattan distance between the ship and an asset.
            This is the "taxicab" distance or sum of the x and y deltas
            between the ship and asset using UTM.'''
        self._set_projection()         
        ship_x,ship_y = self.projection(self.ship_lon,self.ship_lat)        
        asset_x,asset_y = self.projection(self.asset_lon,self.asset_lat)
        self.manhattan_x = asset_x - ship_x
        self.manhattan_y = asset_y - ship_y
        self.manhattan = abs(self.manhattan_x) + abs(self.manhattan_y)

    def _get_euclidian_distance(self):
        '''Compute the euclidian distance between the ship and an asset.
           This is the straight line distance between two points.'''
        self._get_manhattan_distance()
        self.euclidian=math.sqrt((self.manhattan_x)**2 + (self.manhattan_y)**2)
            
    def get_distance_from_ship(self,ship_lat,ship_lon,asset_lat,asset_lon,
                               method="haversine"):
        '''Get an assets distance from the ship using a given method.
        @param ship_lat -- latitude of the ship in decimal degrees.
        @param ship_lon -- longitude of the ship in decimal degrees.
        @param asset_lat -- latitude of the asset in decimal degrees.
        @param asset_lon -- longitude of the asset in decimal degees.
        @param method -- how to calculate the distance. 
                          options: haversine, euclidian, manhattan
        @return -- distance between the ship and asset in meters.
        '''
        self.ship_lat = ship_lat
        self.ship_lon = ship_lon       
        self.asset_lat = asset_lat
        self.asset_lon = asset_lon
        if method == "haversine":
            self._get_haversine_distance()
            distance = self.haversine
        elif method == "euclidian":
            self._get_euclidian_distance()
            distance =  self.euclidian
        elif method == "manhattan":
            self._get_manhattan_distance()
            distance =  self.manhattan
        return int(distance)

    def get_bearing_from_ship(self,ship_lat,ship_lon,asset_lat,asset_lon):  
        '''Get the assets bearing from the ship.
        NOTE: 0 is North, 90 is East, 180 is South, 270 is West.
        @param ship_lat -- latitude of the ship in decimal degrees.
        @param ship_lon -- longitude of the ship in decimal degrees.
        @param asset_lat -- latitude of the asset in decimal degrees.
        @param asset_lon -- longitude of the asset in decimal degees.
        @return -- the bearing in degrees.
        '''
        delta_lambda = math.radians(asset_lon-ship_lon)
        phi_ship = math.radians(ship_lat)
        phi_asset = math.radians(asset_lat)
        y = math.sin(delta_lambda)* math.cos(phi_asset)
        x = (math.cos(phi_ship) * math.sin(phi_asset) - math.sin(phi_ship) 
        * math.cos(phi_asset) * math.cos(delta_lambda))
        bearing = math.degrees(math.atan2(y,x)) % 360
        return int(bearing)  

    def _is_in_range(self,distance,method="haversine"):  
        '''Determine if an asset is within the watch circle of a ship.
        @param distance -- the distance in meters.
        @param method -- how to calculate the distance. 
                          options: haversine, euclidian, manhattan
        @return -- True if it is within the watch circle distance, False if not
        '''
        if method == "haversine":
            self._get_haversine_distance()
            asset_distance = self.haversine
        elif method == "euclidian":
            self._get_euclidian_distance()
            asset_distance = self.euclidian
        elif method == "manhattan":
            self._get_manhattan_distance()
            asset_distance = self.manhattan
        if asset_distance <= distance:
            return True
        else:
            return False
        
    def get_nearby_assets_metadata(self,ship_lat,ship_lon,distance=10000,
                                   method="haversine",online=True):
        '''Get the metadata info of all assets within a watch circle.
        @param ship_lat -- latitude of the ship in decimal degrees.
        @param ship_lon -- longitude of the ship in decimal degrees
        @param distance -- watch circle radius in meters.
        @param method -- how to calculate the distance. 
                          options: haversine, euclidian, manhattan       
        @param online -- only get the metadata for active assets if True.
        @return -- an array of dictionaries that contain asset metadata.
        '''
        self.ship_lat = ship_lat
        self.ship_lon = ship_lon
        assets = self.get_all_assets_metadata(online=online)
        nearby = []
        for asset in assets:
            self.asset_lat = asset['lat']
            self.asset_lon = asset['lon']
            if self._is_in_range(distance,method) is True:
                nearby.append(asset)
            else:
                continue
        if nearby == []:
            return None
        else:
            return nearby
               
    def get_asset_distance_bearing(self,ship_lat,ship_lon,asset,
                                   method="haversine"):
        '''Get an asset's distance and bearing from the ship.
        @param ship_lat -- latitude of the ship in decimal degrees.
        @param ship_lon -- longitude of the ship in decimal degrees
        @param method -- how to calculate the distance. 
                          options: haversine, euclidian, manhattan         
        @return -- the asset's distance in meters and bearing in degrees.
        '''
        
        asset_lat = asset['lat']
        asset_lon = asset['lon']
        distance = self.get_distance_from_ship(ship_lat,ship_lon,
                                               asset_lat,asset_lon,
                                               method = method)
        bearing = self.get_bearing_from_ship(ship_lat,ship_lon,
                                             asset_lat,asset_lon)
        return distance,bearing
        
    
    def get_nearby_distance_bearing(self,ship_lat,ship_lon,distance,
                                    method="haversine",online=True):
        nearby = self.get_nearby_assets_metadata(ship_lat,ship_lon,distance,
                                                 method,online)
        db = []
        for asset in nearby:
            asset_lat = asset['lat']
            asset_lon = asset['lon']        
            d,b = self.get_asset_distance_bearing(ship_lat,ship_lon,
                                                  asset,method)
            info = [asset_lat,asset_lon,d,b]
            db.append(info)
        return db

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