from .application import SimulationApp

def main():
    app = SimulationApp(targets=["SUN", "EARTH", "MOON", "MARS", "JUPITER", "SATURN"]) # most of solar system mass included
    app.run()                                                                          # and moon for Earth-Moon barycenter effects

if __name__ == "__main__":
    main()
