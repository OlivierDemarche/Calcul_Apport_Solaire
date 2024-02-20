import math
from datetime import timedelta
from io import StringIO
import pandas as pd
import requests
from main import LAT, API_KEY, LONG, TODAY, get_irr_vertical_surface, irradiance_trigo, FACTEUR_SOLAIRE, get_solar_position, get_city_name

azimuth, elevation = get_solar_position()


# -------- REAL IRRADIANCE [AT D-7] --------
def get_real_rad_from_api_last_week():
    endpoint = "https://api.solcast.com.au/data/historic/radiation_and_weather"
    data = {"latitude": LAT,
            "longitude": LONG,
            "api_key": API_KEY,
            "start": TODAY - timedelta(days=7, minutes=1),
            "end": TODAY - timedelta(days=7),
            "format": "csv",
            "period": "PT60M"}
    response = requests.get(url=endpoint, params=data)
    if response.status_code == 200:
        # Read data into a DataFrame
        df_data = pd.read_csv(StringIO(response.text))
        # Extract Global Horizontal Irradiance (GHI) from the first row
        ghi_last_week = df_data["ghi"].iloc[0]
        dni_last_week = df_data["dni"].iloc[0]
        return ghi_last_week, dni_last_week
    else:
        print(f"Error: Unable to fetch data. Status code {response.status_code}")
        return 0, 0


def calcul_reel_semaine_pre():
    print("Données réelle : ")
    print(f"Localisation : {get_city_name(latitude=LAT, longitude=LONG)}")
    print(f"Date : {(TODAY-timedelta(days=7)).strftime("%Y-%m-%d")}")
    print(f"Heure : {(TODAY - timedelta(days=7)).strftime("%Hh%M")}\n")
    ghi_last_week, dni_last_week = get_real_rad_from_api_last_week()
    if ghi_last_week != 0:
        dhi_last_week = ghi_last_week - (math.cos((90 - elevation) * (math.pi / 180)) * dni_last_week)
        last_week_irr_pvlib = get_irr_vertical_surface(dni=dni_last_week, dhi=dhi_last_week)
        last_week_irr_trigo = irradiance_trigo(dni=dni_last_week, dhi=dhi_last_week, elevation=elevation,
                                               solar_azimuth=azimuth)
        last_week_irr_finale_pvlib = FACTEUR_SOLAIRE * last_week_irr_pvlib
        last_week_irr_finale_trigo = FACTEUR_SOLAIRE * last_week_irr_trigo
        print("Résultat :\n")
        print(f"Global horizontal irradiance : {ghi_last_week} [W/m2]")
        print(f"Direct normal irradiance : {dni_last_week} [W/m2]")
        print(f"Diffuse horizontal irradiance : {dhi_last_week} [W/m2]")
        print(
            f"\nL'irradiance sur une surface verticale (azimuth 115°) calculée avec PVLIB : {last_week_irr_pvlib} [W/m2]")
        print(
            f"L'irradiance sur une surface verticale (azimuth 115°) calculée par trigonométrique : {last_week_irr_trigo} [W/m2]")
        print(
            f"\nL'irradiance finale qui traverse le double vitrage ( g = {FACTEUR_SOLAIRE}) est de : \nPVLIB : {last_week_irr_finale_pvlib} [W/m2]\nTRIGO : {last_week_irr_finale_trigo} [W/m2]")
    else:
        print("Résultats obtenus de l'API erroné ")


calcul_reel_semaine_pre()
