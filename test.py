"""An example script that simulates a ship sitting at the OSU dock.
It then checks for online NVS assets that are within a 750m (UTM) watch circle 
of the ship. For assets that are in range it checks the age of the data
and also grabs the most recent values for each measurement.
"""

from nanoos.nvs import NVS

nvs = NVS()
if nvs.status() is True:  #If NVS services is online...
    ship_lat = 44.6258  #Lat/Lon of a ship at the OSU dock.
    ship_lon = -124.0451
    radius = 750  #Watch circle size in meters.
    online = True  #Only check for assets that are online.
    nearby = nvs.get_nearby_assets_metadata(ship_lat,ship_lon,radius,online)
    for asset in nearby:  
        asset_lat = asset['lat']
        asset_lon = asset['lon']
        
        dist = nvs.get_distance_from_ship(ship_lat,ship_lon,asset_lat,asset_lon)
        print("{} is {} meters from the ship.".format(asset['name'],dist))
        
        age = nvs.check_asset_data_age(asset)
        print("Data from {} is {} old.".format(asset['name'],age))
        
        data = nvs.get_recent_data(asset)
        print(data)
        
        print('\n\n\n')