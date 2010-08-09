# -*- coding: utf-8 -*-
"""
$Id$

Copyright 2008-2010 Lode Leroy
Copyright 2010 Lars Kruse <devel@sumpfralle.de>

This file is part of PyCAM.

PyCAM is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

PyCAM is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with PyCAM.  If not, see <http://www.gnu.org/licenses/>.
"""

from pycam.Geometry.utils import INFINITE, sqrt
from pycam.Geometry.Point import Point
from pycam.Geometry.intersection import intersect_circle_plane, \
        intersect_circle_point, intersect_circle_line, \
        intersect_cylinder_point, intersect_cylinder_line
from pycam.Cutters.BaseCutter import BaseCutter


try:
    import OpenGL.GL as GL
    import OpenGL.GLU as GLU
    GL_enabled = True
except ImportError:
    GL_enabled = False


class CylindricalCutter(BaseCutter):

    def __init__(self, radius, **kwargs):
        BaseCutter.__init__(self, radius, **kwargs)
        self.axis = Point(0, 0, 1)
        self.center = self.location.sub(Point(0, 0,
                self.get_required_distance()))

    def __repr__(self):
        return "CylindricalCutter<%s,%s>" % (self.location, self.radius)

    def get_shape(self, engine="ODE"):
        if engine == "ODE":
            import ode
            import pycam.Physics.ode_physics as ode_physics
            """ We don't handle the the "additional_distance" perfectly, since
            the "right" shape would be a cylinder with a small flat cap that
            grows to the full expanded radius through a partial sphere. The
            following ascii art shows the idea:
                  | |
                  \_/
            This slight incorrectness should be neglectable and causes no harm.
            """
            additional_distance = self.get_required_distance()
            radius = self.distance_radius
            height = self.height + additional_distance
            center_height = height / 2 - additional_distance
            geom = ode.GeomTransform(None)
            geom_drill = ode.GeomCylinder(None, radius, height)
            geom_drill.setPosition((0, 0, center_height))
            geom.setGeom(geom_drill)
            geom.children = []
            def reset_shape():
                geom.children = []
            def set_position(x, y, z):
                geom.setPosition((x, y, z))
            def extend_shape(diff_x, diff_y, diff_z):
                reset_shape()
                # see http://mathworld.wolfram.com/RotationMatrix.html
                hypotenuse = sqrt(diff_x * diff_x + diff_y * diff_y)
                # Some paths contain two identical points (e.g. a "touch" of
                # the PushCutter) We don't need any extension for these.
                if hypotenuse == 0:
                    return
                cosinus = diff_x / hypotenuse
                sinus = diff_y / hypotenuse
                # create the cyclinder at the other end
                geom_end_transform = ode.GeomTransform(geom.space)
                geom_end_transform.setBody(geom.getBody())
                geom_end = ode.GeomCylinder(None, radius, height)
                geom_end.setPosition((diff_x, diff_y, diff_z + center_height))
                geom_end_transform.setGeom(geom_end)
                # create the block that connects to two cylinders at the end
                rot_matrix_box = (cosinus, sinus, 0.0, -sinus, cosinus, 0.0,
                        0.0, 0.0, 1.0)
                geom_connect_transform = ode.GeomTransform(geom.space)
                geom_connect_transform.setBody(geom.getBody())
                geom_connect = ode_physics.get_parallelepiped_geom(
                        (Point(-hypotenuse / 2, radius, -diff_z / 2),
                        Point(hypotenuse / 2, radius, diff_z / 2),
                        Point(hypotenuse / 2, -radius, diff_z / 2),
                        Point(-hypotenuse / 2, -radius, -diff_z / 2)),
                        (Point(-hypotenuse / 2, radius,
                            self.height - diff_z / 2),
                        Point(hypotenuse / 2,
                            radius, self.height + diff_z / 2),
                        Point(hypotenuse / 2, -radius,
                            self.height + diff_z / 2),
                        Point(-hypotenuse / 2, -radius,
                            self.height - diff_z / 2)))
                geom_connect.setRotation(rot_matrix_box)
                geom_connect.setPosition((hypotenuse / 2, 0, radius))
                geom_connect_transform.setGeom(geom_connect)
                # sort the geoms in order of collision probability
                geom.children.extend([geom_connect_transform,
                        geom_end_transform])
            geom.extend_shape = extend_shape
            geom.reset_shape = reset_shape
            self.shape[engine] = (geom, set_position)
            return self.shape[engine]

    def to_OpenGL(self):
        if not GL_enabled:
            return
        GL.glPushMatrix()
        GL.glTranslate(self.center.x, self.center.y, self.center.z)
        if not hasattr(self, "_cylinder"):
            self._cylinder = GLU.gluNewQuadric()
        GLU.gluCylinder(self._cylinder, self.radius, self.radius, self.height,
                10, 10)
        if not hasattr(self, "_disk"):
            self._disk = GLU.gluNewQuadric()
        GLU.gluDisk(self._disk, 0, self.radius, 10, 10)
        GL.glPopMatrix()

    def moveto(self, location):
        BaseCutter.moveto(self, location)
        self.center = location.sub(Point(0, 0, self.get_required_distance()))

    def intersect_circle_plane(self, direction, triangle):
        (ccp, cp, d) = intersect_circle_plane(self.center, self.distance_radius,
                direction, triangle)
        if ccp:
            cl = cp.add(self.location.sub(ccp))
            return (cl, ccp, cp, d)
        return (None, None, None, INFINITE)

    def intersect_circle_triangle(self, direction, triangle):
        (cl, ccp, cp, d) = self.intersect_circle_plane(direction, triangle)
        if cp and triangle.point_inside(cp):
            return (cl, d)
        return (None, INFINITE)

    def intersect_circle_point(self, direction, point):
        (ccp, cp, l) = intersect_circle_point(self.center, self.axis,
                self.distance_radius, self.distance_radiussq, direction, point)
        if ccp:
            cl = cp.add(self.location.sub(ccp))
            return (cl, ccp, cp, l)
        return (None, None, None, INFINITE)

    def intersect_circle_vertex(self, direction, point):
        (cl, ccp, cp, l) = self.intersect_circle_point(direction, point)
        return (cl, l)

    def intersect_circle_line(self, direction, edge):
        (ccp, cp, l) = intersect_circle_line(self.center, self.axis,
                self.distance_radius, self.distance_radiussq, direction, edge)
        if ccp:
            cl = cp.add(self.location.sub(ccp))
            return (cl, ccp, cp, l)
        return (None, None, None, INFINITE)

    def intersect_circle_edge(self, direction, edge):
        (cl, ccp, cp, l) = self.intersect_circle_line(direction, edge)
        if cp:
            # check if the contact point is between the endpoints
            m = cp.sub(edge.p1).dot(edge.dir)
            if (m < 0) or (m > edge.len):
                return (None, INFINITE)
        return (cl, l)

    def intersect_cylinder_point(self, direction, point):
        (ccp, cp, l) = intersect_cylinder_point(self.center, self.axis,
                self.distance_radius, self.distance_radiussq, direction, point)
        # offset intersection
        if ccp:
            cl = cp.add(self.location.sub(ccp))
            return (cl, ccp, cp, l)
        return (None, None, None, INFINITE)

    def intersect_cylinder_vertex(self, direction, point):
        (cl, ccp, cp, l) = self.intersect_cylinder_point(direction, point)
        if ccp and ccp.z < self.center.z:
            return (None, INFINITE)
        return (cl, l)

    def intersect_cylinder_line(self, direction, edge):
        (ccp, cp, l) = intersect_cylinder_line(self.center, self.axis,
                self.distance_radius, self.distance_radiussq, direction, edge)
        # offset intersection
        if ccp:
            cl = cp.add(self.location.sub(ccp))
            return (cl, ccp, cp, l)
        return (None, None, None, INFINITE)

    def intersect_cylinder_edge(self, direction, edge):
        (cl, ccp, cp, l) = self.intersect_cylinder_line(direction, edge)
        if not ccp:
            return (None, INFINITE)
        m = cp.sub(edge.p1).dot(edge.dir)
        if (m < 0) or (m > edge.len):
            return (None, INFINITE)
        if ccp.z < self.center.z:
            return (None, INFINITE)
        return (cl, l)

    def intersect_plane(self, direction, triangle):
        return self.intersect_circle_plane(direction, triangle)

    def intersect(self, direction, triangle):
        (cl_t, d_t) = self.intersect_circle_triangle(direction, triangle)
        d = INFINITE
        cl = None
        if d_t < d:
            d = d_t
            cl = cl_t
        if cl and (direction.x == 0) and (direction.y == 0):
            return (cl, d)
        (cl_e1, d_e1) = self.intersect_circle_edge(direction, triangle.e1)
        (cl_e2, d_e2) = self.intersect_circle_edge(direction, triangle.e2)
        (cl_e3, d_e3) = self.intersect_circle_edge(direction, triangle.e3)
        if d_e1 < d:
            d = d_e1
            cl = cl_e1
        if d_e2 < d:
            d = d_e2
            cl = cl_e2
        if d_e3 < d:
            d = d_e3
            cl = cl_e3
        if cl and (direction.x == 0) and (direction.y == 0):
            return (cl, d)
        (cl_p1, d_p1) = self.intersect_circle_vertex(direction, triangle.p1)
        (cl_p2, d_p2) = self.intersect_circle_vertex(direction, triangle.p2)
        (cl_p3, d_p3) = self.intersect_circle_vertex(direction, triangle.p3)
        if d_p1 < d:
            d = d_p1
            cl = cl_p1
        if d_p2 < d:
            d = d_p2
            cl = cl_p2
        if d_p3 < d:
            d = d_p3
            cl = cl_p3
        if cl and (direction.x == 0) and (direction.y == 0):
            return (cl, d)
        if (direction.x != 0) or (direction.y != 0):
            (cl_p1, d_p1) = self.intersect_cylinder_vertex(direction,
                    triangle.p1)
            (cl_p2, d_p2) = self.intersect_cylinder_vertex(direction,
                    triangle.p2)
            (cl_p3, d_p3) = self.intersect_cylinder_vertex(direction,
                    triangle.p3)
            if d_p1 < d:
                d = d_p1
                cl = cl_p1
            if d_p2 < d:
                d = d_p2
                cl = cl_p2
            if d_p3 < d:
                d = d_p3
                cl = cl_p3
            (cl_e1, d_e1) = self.intersect_cylinder_edge(direction, triangle.e1)
            (cl_e2, d_e2) = self.intersect_cylinder_edge(direction, triangle.e2)
            (cl_e3, d_e3) = self.intersect_cylinder_edge(direction, triangle.e3)
            if d_e1 < d:
                d = d_e1
                cl = cl_e1
            if d_e2 < d:
                d = d_e2
                cl = cl_e2
            if d_e3 < d:
                d = d_e3
                cl = cl_e3
        return (cl, d)

