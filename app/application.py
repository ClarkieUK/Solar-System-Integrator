from win32api import GetSystemMetrics
import glfw
from OpenGL.GL import *
from OpenGL.GL.shaders import compileProgram, compileShader
import glm

import numpy as np
from datetime import datetime
import pandas as pd  

# project modules
from engine.camera import Camera
from engine.shader import Shader
from engine.sphere import Sphere
from simulation.body import Bodies
from simulation.load_bodies import LoadBodies
from simulation.transferorbit import Spaceship
from simulation.integrators import (
    update_bodies_dormand_prince,
    update_bodies_fixed_dormand_prince
)
from utils.deltatime import TimeManager


class SimulationApp:
    def __init__(self,  targets: list, width: int = 900, height: int = 900) -> None:
        # window
        self.width = width
        self.height = height
        self.window = None

        # camera & input state
        self.main_camera = Camera()
        self.first_mouse = True
        self.last_x_position = 0.0
        self.last_y_position = 0.0

        self.simming = False
        self.simming_pressed = False

        self.launch = False
        self.launch_pressed = False
        self.satellite_exists = False

        # integration step sizes
        self.fehlberg_timestep = (3.154e7) * 1 / (16 * 144)
        self.prince_timestep = (3.154e7) * 1 / (160 * 144)

        # constants
        self.G = 6.67430e-11
        self.AU = 1.496e11
        self.scale = 8 / self.AU

        # OpenGL resources
        self.sphere_shader = None
        self.orbits_shader = None
        self.skybox_shader = None

        # simulation state
        self.targets = targets
        self.bodies_state: Bodies | None = None
        self.skybox = None
        self.satellite = None

    # ------------------------------------------------------------------
    # GLFW / window setup
    # ------------------------------------------------------------------
    def init_window(self) -> None:
        if not glfw.init():
            raise Exception("glfw library not found...")

        self.window = glfw.create_window(self.width, self.height, "", None, None)
        if not self.window:
            glfw.terminate()
            raise Exception("Failed to create GLFW window")

        # centre window
        xbuf = (GetSystemMetrics(0) - self.width) / 2
        ybuf = (GetSystemMetrics(1) - self.height) / 2
        glfw.set_window_pos(self.window, int(xbuf), int(ybuf))

        # callbacks
        glfw.set_window_size_callback(self.window, self.window_resize)
        glfw.set_cursor_pos_callback(self.window, self.mouse_callback)
        glfw.set_scroll_callback(self.window, self.scroll_callback)

        # context & cursor
        glfw.make_context_current(self.window)
        glfw.set_input_mode(self.window, glfw.CURSOR, glfw.CURSOR_DISABLED)

        # general GL state
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glClearColor(0, 0, 0, 1)
        glfw.swap_interval(0)  # uncap FPS

    # ------------------------------------------------------------------
    # Scene / simulation setup
    # ------------------------------------------------------------------
    def init_scene(self) -> None:
        # shaders
        self.sphere_shader = Shader("pixilated_noise.vs", "pixilated_noise.fs")
        self.orbits_shader = Shader("orbit.vs", "orbit.fs")
        self.skybox_shader = Shader("skybox.vs", "skybox.fs")

        # bodies
        bodies_to_load = self.targets
        all_bodies = LoadBodies("data/body_data.csv", bodies_to_load)
        self.bodies_state = Bodies.from_bodies(all_bodies)
        self.bodies_state.check_csvs()

        # optional skybox sphere (radius, segments)
        self.skybox = Sphere(2500, 15)

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------
    def process_input_camera(self, delta_time: float) -> None:
        if glfw.get_key(self.window, glfw.KEY_ESCAPE) == glfw.PRESS:
            try:
                from simulation.integrators import step_sizes, global_errors

                step_sizes_arr = np.array(step_sizes)
                global_errors_arr = np.array(global_errors)
                np.savez(
                    "integration_data.npz",
                    step_sizes=step_sizes_arr,
                    global_errors=global_errors_arr,
                )
            except Exception:
                pass

            glfw.set_window_should_close(self.window, True)

        if glfw.get_key(self.window, glfw.KEY_W) == glfw.PRESS:
            self.main_camera.processKeyboard("FORWARD", delta_time)
        if glfw.get_key(self.window, glfw.KEY_S) == glfw.PRESS:
            self.main_camera.processKeyboard("BACKWARD", delta_time)
        if glfw.get_key(self.window, glfw.KEY_A) == glfw.PRESS:
            self.main_camera.processKeyboard("LEFT", delta_time)
        if glfw.get_key(self.window, glfw.KEY_D) == glfw.PRESS:
            self.main_camera.processKeyboard("RIGHT", delta_time)
        if glfw.get_key(self.window, glfw.KEY_LEFT_CONTROL) == glfw.PRESS:
            self.main_camera.processKeyboard("DOWN", delta_time)
        if glfw.get_key(self.window, glfw.KEY_SPACE) == glfw.PRESS:
            self.main_camera.processKeyboard("UP", delta_time)
        if glfw.get_key(self.window, glfw.KEY_LEFT_SHIFT) == glfw.PRESS:
            self.main_camera.processKeyboardSpeed("SPEED_UP", delta_time)
        if glfw.get_key(self.window, glfw.KEY_LEFT_SHIFT) == glfw.RELEASE:
            self.main_camera.processKeyboardSpeed("SLOW_DOWN", delta_time)

    def process_input_sim(self) -> None:
        if glfw.get_key(self.window, glfw.KEY_R) == glfw.PRESS:
            if not self.simming_pressed:
                self.simming = not self.simming
                self.simming_pressed = True

        if glfw.get_key(self.window, glfw.KEY_R) == glfw.RELEASE:
            self.simming_pressed = False

    def process_input_launch(self) -> None:
        if glfw.get_key(self.window, glfw.KEY_L) == glfw.PRESS:
            if not self.launch_pressed:
                self.launch = not self.launch
                self.launch_pressed = True

        if glfw.get_key(self.window, glfw.KEY_L) == glfw.RELEASE:
            self.launch_pressed = False

    def process_input_scale(self) -> None:
        if glfw.get_key(self.window, glfw.KEY_UP) == glfw.PRESS:
            self.scale -= 0.01 / self.AU
        if glfw.get_key(self.window, glfw.KEY_DOWN) == glfw.PRESS:
            self.scale += 0.01 / self.AU

    # ------------------------------------------------------------------
    # GLFW callbacks
    # ------------------------------------------------------------------
    def window_resize(self, window, width, height):
        self.width = width
        self.height = height
        glViewport(0, 0, width, height)

    def mouse_callback(self, window, x_position, y_position):
        if self.first_mouse:
            self.last_x_position = x_position
            self.last_y_position = y_position
            self.first_mouse = False

        xoffset = float(x_position - self.last_x_position)
        yoffset = float(self.last_y_position - y_position)
        self.last_x_position = float(x_position)
        self.last_y_position = float(y_position)

        self.main_camera.processMouseMovement(xoffset, yoffset, True)

    def scroll_callback(self, window, xoffset, yoffset):
        self.main_camera.processMouseScroll(yoffset)

    # ------------------------------------------------------------------
    # Simulation step
    # ------------------------------------------------------------------
    def _handle_launch_logic(self) -> None:
        """Handle launch trigger and satellite creation/propagation."""
        if not self.simming:
            return

        # toggle launch flag from input
        self.process_input_launch()

        # launch date condition
        current_unix = TimeManager.unix_start + TimeManager.simulated_time
        launch_date = datetime.strptime("2024-12-20", "%Y-%m-%d").timestamp()

        if current_unix >= launch_date and self.launch:
            # empty buffer of old instance information if multiple launches
            if self.satellite_exists and self.satellite is not None:
                self.satellite.satellite.file.seek(0)
                self.satellite.satellite.file.truncate(0)

            self.satellite = Spaceship("EARTH", "MARS")
            self.satellite.launch(current_unix, self.bodies_state)
            self.satellite.bodies_state.check_csvs()

            self.launch = False
            self.satellite_exists = True

        # propagate satellite if it exists
        if self.satellite_exists and self.satellite is not None:
            if self.satellite.mission_time >= self.satellite.t:
                # satellite mission complete – no second impulse / shutdown
                self.satellite_mission_complete = True
                return

            # log satellite state
            self.satellite.satellite.log(
                TimeManager.sim_date.translate({ord(","): None})
            )

            #!!! propagate satellite using the same timestep as the main system
            # we ignore the returned suggested dt here to keep it locked
            update_bodies_fixed_dormand_prince(
                self.satellite.bodies_state, self.prince_timestep
            )

            self.satellite.mission_time += self.prince_timestep

    def _step_simulation(self):
        if not self.simming:
            return

        self._handle_launch_logic()

        # if cleanup happened:
        if hasattr(self, "logging_enabled") and not self.logging_enabled:
            return

        # log bodies
        for body in self.bodies_state.bodies:
            body.log(TimeManager.sim_date.translate({ord(","): None}))

        # timestep update
        self.prince_timestep = update_bodies_dormand_prince(
            self.bodies_state, self.prince_timestep
        )

        TimeManager.simulated_time += self.prince_timestep

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def _render_frame(self) -> None:
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        # view and projection from camera
        view = self.main_camera.getViewMatrix()
        projection = glm.perspective(
            glm.radians(self.main_camera.Zoom),
            self.width / self.height,
            0.1,
            1500.0,
        )

        # shader uniforms
        for shader in (self.sphere_shader, self.orbits_shader, self.skybox_shader):
            shader.setMat4("view", view)
            shader.setMat4("projection", projection)
            shader.setFloat("iTime", glfw.get_time())

        # draw planetary bodies
        for body in self.bodies_state:
            body.draw(self.sphere_shader, self.scale, self.simming)
            body.draw_orbit(self.orbits_shader, self.scale)

        # draw satellite if exists
        if self.satellite_exists and self.satellite is not None:
            for body in self.satellite.bodies_state:
                body.draw(self.sphere_shader, self.scale, self.simming)
                body.draw_orbit(self.orbits_shader, self.scale)

        # optional skybox 
        # self.skybox.draw(self.skybox_shader, np.array([0.0, 0.0, 0.0]), 1)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    def run(self) -> None:
        self.init_window()
        self.init_scene()

        try:
            while not glfw.window_should_close(self.window):
                # delta time & simulated date
                delta_time = TimeManager.calculate_deltatime(glfw.get_time())
                TimeManager.update_sim_date()

                # update window title as framerate
                if delta_time > 0:
                    fps = 1.0 / delta_time
                    glfw.set_window_title(self.window, f"{fps:.1f}")
                else:
                    glfw.set_window_title(self.window, "inf")

                # per-second tasks
                TimeManager.update_average_framerate(glfw.get_time())

                # input
                self.process_input_camera(delta_time)
                self.process_input_sim()
                self.process_input_scale()

                # simulate
                self._step_simulation()

                # render
                self._render_frame()

                # swap & poll
                glfw.poll_events()
                glfw.swap_buffers(self.window)
        finally:
            # cleanup
            if self.bodies_state is not None:
                for body in self.bodies_state.bodies:
                    try:
                        body.file.close()
                    except Exception:
                        pass

            if self.satellite_exists and self.satellite is not None:
                try:
                    self.satellite.satellite.file.close()
                except Exception:
                    pass

            glfw.terminate()