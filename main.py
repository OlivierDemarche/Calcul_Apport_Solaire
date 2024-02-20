import math
import os
from datetime import datetime as dt
import pandas as pd
import pvlib
import requests
from geopy.geocoders import Nominatim

# --------------------------------------------------------------
# -------------------------- PARAMETRES ------------------------
# --------------------------------------------------------------
BAT_AZIMUTH = [115, 205]  # Azimuth des différentes façades
SURFACE_VITRAGE = [153.5, 25]  # Surface de vitrage en présence sur les façades respectives
FACTEUR_SOLAIRE = 0.37  # Facteur solaire pour double vitrage HR
ANGLE_CONDITION = 10  # Condition d'élévation solaire minimale (dépends de la présence de bâtiment, d'ombrage,...)
LAT = float(os.environ["LAT"])  # Latitude du lieu à étudier
LONG = float(os.environ["LONG"])  # Longitude du lieu à étudier
ALTITUDE = 66  # Altitude du lieu à étudier
TODAY = dt.now()  # Date
RHO = 0.15  # Albedo du sol en ville

# --------------------------------------------------------------
# ------------------------ CONSTANTS ---------------------------
# --------------------------------------------------------------

API_KEY = os.environ["API_KEY"]
API_KEY_OWM = os.environ["API_KEY_OWM"]

# --------------------------------------------------------------
# --------------------------- API ------------------------------
# --------------------------------------------------------------


# -------- CLOUD COVERAGE DATA [%] --------
def get_cloud_coverage():
    endpoint = "http://api.openweathermap.org/data/2.5/weather"
    params = {
        'lat': LAT,
        "lon": LONG,
        'appid': API_KEY_OWM, }
    try:
        response = requests.get(endpoint, params=params)
        data = response.json()

        if response.status_code == 200:
            nuages = data['clouds']['all']
            return nuages
        else:
            print(response.text)
            return 0
    except Exception as e:
        print(f"Erreur lors de la requête : {str(e)}")
        return 0


# --------------------------------------------------------------
# ------------------------ IRRADIANCE --------------------------
# --------------------------------------------------------------


# -------- CLEAR SKY DATA --------
def get_clear_sky_rad(latitude, longitude):
    date = pd.date_range(TODAY, TODAY, freq='1h', tz='UTC')
    # Créez une instance de la classe Location avec les coordonnées de l'endroit souhaité
    location = pvlib.location.Location(latitude, longitude)
    # Utilisez la fonction get_clearsky pour obtenir les estimations
    clearsky = location.get_clearsky(date, model="ineichen")
    clear_sky_dni = clearsky["dni"].values[0]
    clear_sky_dhi = clearsky["dhi"].values[0]
    clear_sky_ghi = clearsky["ghi"].values[0]
    ghi_verif = math.cos((90 - elevation) * (math.pi / 180)) * clear_sky_dni + clear_sky_dhi
    return clear_sky_dni, clear_sky_dhi, clear_sky_ghi


# -------- CALCULATE ON ORIENTED SURFACE WITH PVLIB --------
def get_irr_vertical_surface(dni, dhi, ghi, azimtuh_facade, solar_azimuth):
    weather_data = pd.DataFrame(index=[TODAY])
    weather_data['dni'] = dni
    if dni_orientation_condition(facade_azimuth=azimtuh_facade, solar_azimuth=solar_azimuth):
        weather_data['dni'] = dni  # Direct Normal Irradiance (W/m^2)
    else:
        weather_data['dni'] = 0  # Direct Normal Irradiance (W/m^2)
    weather_data['dhi'] = dhi  # Diffuse Horizontal Irradiance (W/m^2)
    weather_data['ghi'] = ghi
    # Calcul de la position solaire pour l'heure spécifique
    solpos = pvlib.solarposition.get_solarposition(time=weather_data.index, latitude=LAT, longitude=LONG)
    # Calcul de l'irradiance sur la paroi sud-est verticale
    effective_irradiance_wall = pvlib.irradiance.get_total_irradiance(surface_tilt=90, surface_azimuth=azimtuh_facade,
                                                                      solar_zenith=solpos['apparent_zenith'],
                                                                      solar_azimuth=solpos['azimuth'],
                                                                      dni=weather_data['dni'],
                                                                      ghi=weather_data['ghi'],
                                                                      dhi=weather_data['dhi'],
                                                                      dni_extra=None,
                                                                      albedo=0.15)
    return effective_irradiance_wall['poa_global'].values[0]


# -------- CALCULATE ON ORIENTED SURFACE WITH TRIGO --------
def irradiance_trigo(dni, dhi, ghi, solar_angle, solar_azimuth, facade_azimuth):
    # Conversion des angles en radians si nécessaire
    elevation_rad = solar_angle * (math.pi / 180)
    solar_azimuth_rad = solar_azimuth * (math.pi / 180)
    facade_azimuth_rad = facade_azimuth * (math.pi / 180)
    if ANGLE_CONDITION < solar_angle < 90 and dni_orientation_condition(facade_azimuth=facade_azimuth, solar_azimuth=solar_azimuth):
        direct_component = dni * math.cos(elevation_rad) * math.cos(solar_azimuth_rad - facade_azimuth_rad)
    else:
        direct_component = 0
    b = dhi * ((1 + math.cos(90 * (math.pi / 180))) / 2) + ((dhi * math.sin(elevation_rad))/2)  # radiateur diffuse isotrope + diffusion vers le bas
    c = ghi * RHO * ((1 - math.cos(elevation_rad)) / 2)
    diffuse = b + c
    irr = direct_component + diffuse
    return irr


# --------------------------------------------------------------
# ------------------------ OTHERS FUNCTIONS --------------------
# --------------------------------------------------------------

def dni_orientation_condition(facade_azimuth, solar_azimuth):
    if facade_azimuth < 90:
        condition_inf = 360 - (90 - facade_azimuth)
        condition_sup = facade_azimuth + 90
    elif facade_azimuth > 270:
        condition_inf = facade_azimuth - 90
        condition_sup = 0 + (90 - (360 - facade_azimuth))
    else:
        condition_inf = facade_azimuth - 90
        condition_sup = facade_azimuth + 90
    if condition_inf < solar_azimuth < condition_sup:
        return True
    else:
        return False


# -------- DNI CORRECTION WITH CLOUD COVERAGE --------
def calculate_real_dni(dni):
    return dni * (1 - (cloud_percentage / 100))


# -------- GET SOLAR AZIMUTH AND ELEVATION (TILT) [°] --------
def get_solar_position():
    data = pd.DataFrame(index=[TODAY])
    # Calcul de la position solaire
    solar_position = pvlib.solarposition.get_solarposition(data.index, LAT, LONG, ALTITUDE, method='nrel_numpy')
    # Récupération de l'azimut et de l'angle d'inclinaison du soleil
    solar_azimuth = solar_position['azimuth'].values[0]
    tilt = solar_position['elevation'].values[0]
    return solar_azimuth, tilt


# -------- GET LOCALISATION FROM LAT/LONG --------

def get_direction(orientation):
    directions = {
        (0, 11.25): 'Nord',
        (11.25, 33.75): 'Nord-Nord-Est',
        (33.75, 56.25): 'Nord-Est',
        (56.25, 78.75): 'Est-Nord-Est',
        (78.75, 101.25): 'Est',
        (101.25, 123.75): 'Est-Sud-Est',
        (123.75, 146.25): 'Sud-Est',
        (146.25, 168.75): 'Sud-Sud-Est',
        (168.75, 191.25): 'Sud',
        (191.25, 213.75): 'Sud-Sud-Ouest',
        (213.75, 236.25): 'Sud-Ouest',
        (236.25, 258.75): 'Ouest-Sud-Ouest',
        (258.75, 281.25): 'Ouest',
        (281.25, 303.75): 'Ouest-Nord-Ouest',
        (303.75, 326.25): 'Nord-Ouest',
        (326.25, 348.75): 'Nord-Nord-Ouest',
        (348.75, 360): 'Nord'
    }
    for angle_range, direction in directions.items():
        if angle_range[0] <= orientation < angle_range[1]:
            return direction
    return 'Inconnu'


def get_city_name(latitude, longitude):
    geolocator = Nominatim(user_agent="my_geocoder")
    location = geolocator.reverse((latitude, longitude), language='fr')
    address = location.address if location else None
    return address


def printing_results(correction, cloud, ghi, dni, dhi, irr_pvlib, irr_trigo, irr_final_pvlib, irr_final_trigo,
                     pvlib_result, trigo_result, facteur_solaire, side, facade_azimuth, window_surface):
    if correction:
        print("\n--------------------------------------------------------")
        print("Valeurs corrigées AVEC COUVERTURE NUAGEUSE :")
        print("--------------------------------------------------------")
        print(f"Couverture nuageuse : {cloud} %")
    else:
        print("\n--------------------------------------------------------")
        print("Valeurs calculées en cas de CIEL CLAIR :")
        print("--------------------------------------------------------")
    print(f"ghi: {ghi}  [W/m²] (Irradiation Globale)\ndni: {dni}  [W/m²] (Irradiation Normale Direct)\ndhi: {dhi}  [W/m²] (Irradiation Horizontale Diffuse)")
    print(f"\nIrradiance sur une surface verticale (azimuth {facade_azimuth}) :")
    print(f"Calculée avec PVLIB : {irr_pvlib} [W/m2]")
    print(f"Calculée par trigonométrique : {irr_trigo} [W/m2]")
    print(f"\nIrradiance finale qui traverse le double vitrage ( g = {facteur_solaire}) est de : \nPVLIB : {irr_final_pvlib} [W/m2]\nTRIGO : {irr_final_trigo} [W/m2]")
    print(f"\nRésultats de l'apport solaire sur la façade {side} comportant {window_surface} m2 de double vitrage HR (g={facteur_solaire}) :")
    print(f"Calculé via PVLIB : {pvlib_result} Watts")
    print(f"Calculé via TRIGO : {trigo_result} Watts")


# --------------------------------------------------------------
# -------------------------- MAIN FUNCTION ---------------------
# --------------------------------------------------------------

def solar_gain_building_side(azimtuh_facade, solar_angle, solar_azimuth, dni, dhi, ghi, corrected_dni, window_surface, facteur_solaire):
    irr_pvlib = get_irr_vertical_surface(dni=dni, dhi=dhi, ghi=ghi, solar_azimuth=solar_azimuth, azimtuh_facade=azimtuh_facade)
    irr_trigo = irradiance_trigo(dni=dni, dhi=dhi, ghi=ghi, solar_angle=solar_angle, solar_azimuth=solar_azimuth, facade_azimuth=azimtuh_facade)
    irr_finale_pvlib = facteur_solaire * irr_pvlib
    irr_finale_trigo = facteur_solaire * irr_trigo
    apport_puissance_pvlib = window_surface * irr_finale_pvlib
    apport_puissance_trigo = window_surface * irr_finale_trigo
    # -------- CORRECTIONS DES PARAMETRES EN PRESENCE DE COUVERTURE NUAGEUSE --------
    corr_irr_pvlib = get_irr_vertical_surface(dni=corrected_dni, dhi=dhi, ghi=ghi, solar_azimuth=solar_azimuth, azimtuh_facade=azimtuh_facade)
    corr_irr_trigo = irradiance_trigo(dni=corrected_dni, dhi=dhi, ghi=ghi, solar_angle=solar_angle, solar_azimuth=solar_azimuth, facade_azimuth=azimtuh_facade)
    corr_irr_finale_pvlib = facteur_solaire * corr_irr_pvlib
    corr_irr_finale_trigo = facteur_solaire * corr_irr_trigo
    corr_apport_puissance_pvlib = window_surface * corr_irr_finale_pvlib
    corr_apport_puissance_trigo = window_surface * corr_irr_finale_trigo
    orientation_facade = get_direction(azimtuh_facade)
    print(f"\nFaçade {orientation_facade} : ")
    # -------- AFFICHAGE RESULTATS --------
    printing_results(correction=False,
                     cloud=0,
                     ghi=ghi,
                     dni=dni,
                     dhi=dhi,
                     irr_pvlib=irr_pvlib,
                     irr_trigo=irr_trigo,
                     irr_final_pvlib=irr_finale_pvlib,
                     irr_final_trigo=irr_finale_trigo,
                     pvlib_result=apport_puissance_pvlib,
                     trigo_result=apport_puissance_trigo,
                     facteur_solaire=facteur_solaire,
                     side=orientation_facade,
                     facade_azimuth=azimtuh_facade,
                     window_surface=window_surface)
    printing_results(correction=True,
                     cloud=cloud_percentage,
                     ghi=ghi,
                     dni=cloud_corrected_dni,
                     dhi=dhi,
                     irr_pvlib=corr_irr_pvlib,
                     irr_trigo=corr_irr_trigo,
                     irr_final_pvlib=corr_irr_finale_pvlib,
                     irr_final_trigo=corr_irr_finale_trigo,
                     pvlib_result=corr_apport_puissance_pvlib,
                     trigo_result=corr_apport_puissance_trigo,
                     facteur_solaire=facteur_solaire,
                     side=orientation_facade,
                     facade_azimuth=azimtuh_facade,
                     window_surface=window_surface)
    return corr_apport_puissance_pvlib, corr_apport_puissance_trigo


# --------------------------------------------------------------
# -------------------------- MAIN LOGIC ------------------------
# --------------------------------------------------------------

if __name__ == "__main__":
    # -------- CALCUL DES PARAMETRES EN CAS DE CIEL CLAIR --------
    azimuth, elevation = get_solar_position()
    dni, dhi, ghi = get_clear_sky_rad(LAT, LONG)
    city_name = get_city_name(LAT, LONG)
    cloud_percentage = get_cloud_coverage()
    cloud_corrected_dni = calculate_real_dni(dni=dni)
    # ------------ AFFICHAGE DES DONNEES -----------
    print("------------------------------------------------------------------------------------------------")
    print("Données :")
    print("------------")
    print(f"Localisation : {city_name} \nDate : {TODAY.strftime("%d-%m-%Y")}\nHeure : {TODAY.strftime("%Hh%M")}")
    print(f"Azimut du soleil: {azimuth} °")
    print(f"Angle d'inclinaison du soleil: {elevation} °")
    print(f"Le calcul sera effectué sur {len(BAT_AZIMUTH)} façade(s)")
    # ------------ CALCULS DES APPORTS PAR FACADES -----------
    pv_lib_total = 0
    trigo_total = 0
    for facade, surface in zip(BAT_AZIMUTH, SURFACE_VITRAGE):
        print("------------------------------------------------------------------------------------------------")
        apport_pvlib, apport_trigo = solar_gain_building_side(azimtuh_facade=facade,
                                                              solar_angle=elevation,
                                                              solar_azimuth=azimuth,
                                                              dni=dni, dhi=dhi,
                                                              ghi=ghi,
                                                              corrected_dni=cloud_corrected_dni,
                                                              window_surface=surface,
                                                              facteur_solaire=FACTEUR_SOLAIRE)
        pv_lib_total += apport_pvlib
        trigo_total += apport_trigo
    # ------------ AFFICHAGE DES RESULTATS -----------
    print("\n--------------------------------------------------------")
    print("Résultats :")
    print("--------------------------------------------------------")
    print(f"L'apport solaire total du bâtiment calculé à via PVLIB est de : {pv_lib_total} Watts ")
    print(f"L'apport solaire total du bâtiment calculé à via Trigonométrie est de : {trigo_total} Watts")
    print("------------------------------------------------------------------------------------------------")
