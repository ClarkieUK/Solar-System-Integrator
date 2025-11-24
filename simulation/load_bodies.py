import pandas as pd
import numpy as np
from simulation.body import Body  # assuming Body is defined in body.py
from engine.colors import color_map  

def LoadBodies(csv_path: str, bodies_to_load: list):

    df = pd.read_csv(csv_path)

    # Filter only the bodies we want
    if bodies_to_load is not None:
        df = df[df["id"].isin(bodies_to_load)]

    bodies = []
    for _, row in df.iterrows():
        pos = np.array([
            np.longdouble(row["position_x"]),
            np.longdouble(row["position_y"]),
            np.longdouble(row["position_z"])
        ], dtype=np.longdouble) * 1e3  # Convert km to m

        vel = np.array([
            np.longdouble(row["velocity_x"]),
            np.longdouble(row["velocity_y"]),
            np.longdouble(row["velocity_z"])
        ], dtype=np.longdouble) * 1e3  # Convert km/s to m/s

        body = Body(
            row["id"],
            color_map[row["color_name"]],
            np.longdouble(row["radius"]),
            pos,
            vel,
            np.longdouble(row["mass"])
        )
        bodies.append(body)

    return np.array(bodies)
