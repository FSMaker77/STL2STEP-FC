"""OpenGL 3D mesh preview widget (self-contained, no extra dependencies)."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QSurfaceFormat, QMouseEvent, QWheelEvent
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtOpenGL import (
    QOpenGLBuffer,
    QOpenGLShader,
    QOpenGLShaderProgram,
    QOpenGLVertexArrayObject,
)

from ..core.mesh import Mesh


_VERT = """
#version 330 core
layout(location = 0) in vec3 aPos;
layout(location = 1) in vec3 aNormal;
uniform mat4 uMVP;
uniform mat4 uModel;
uniform mat3 uNormalMat;
out vec3 vNormal;
out vec3 vPos;
void main() {
    vec4 world = uModel * vec4(aPos, 1.0);
    vPos = world.xyz;
    vNormal = uNormalMat * aNormal;
    gl_Position = uMVP * vec4(aPos, 1.0);
}
"""

_FRAG = """
#version 330 core
in vec3 vNormal;
in vec3 vPos;
uniform vec3 uLightDir;
uniform vec3 uBaseColor;
out vec4 fragColor;
void main() {
    vec3 n = normalize(vNormal);
    vec3 l = normalize(uLightDir);
    float diff = max(dot(n, l), 0.0);
    float amb = 0.32;
    vec3 col = uBaseColor * (amb + 0.75 * diff);
    float rim = pow(1.0 - abs(dot(n, normalize(-vPos))), 2.0);
    col += vec3(0.06) * rim;
    fragColor = vec4(col, 1.0);
}
"""


class MeshPreview(QOpenGLWidget):
    """Interactive shaded preview of a triangle mesh."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 240)
        fmt = QSurfaceFormat()
        fmt.setVersion(3, 3)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        fmt.setDepthBufferSize(24)
        fmt.setSamples(4)
        self.setFormat(fmt)
        self._mesh: Mesh | None = None
        self._rot_x = -30.0
        self._rot_y = -35.0
        self._zoom = 1.0
        self._last = QPoint()
        self._program: QOpenGLShaderProgram | None = None
        self._vao: QOpenGLVertexArrayObject | None = None
        self._vbo: QOpenGLBuffer | None = None
        self._n_verts = 0
        self._center = np.zeros(3)
        self._scale = 1.0
        self._base_color = (0.62, 0.70, 0.88)
        self._empty = True

    def set_mesh(self, mesh: Mesh | None) -> None:
        self._mesh = mesh
        if mesh is not None and mesh.n_faces > 0:
            lo, hi = mesh.bbox
            self._center = 0.5 * (lo + hi)
            diag = float(np.linalg.norm(hi - lo))
            self._scale = 1.0 / diag if diag > 1e-9 else 1.0
            self._empty = False
        else:
            self._empty = True
        self._upload()
        self.update()

    # ------------------------------------------------------------------ GL
    def initializeGL(self) -> None:
        self._program = QOpenGLShaderProgram()
        if not self._program.addShaderFromSourceCode(QOpenGLShader.Vertex, _VERT):
            print("vertex shader:", self._program.log())
        if not self._program.addShaderFromSourceCode(QOpenGLShader.Fragment, _FRAG):
            print("fragment shader:", self._program.log())
        if not self._program.link():
            print("link:", self._program.log())
        self._upload()

    def _upload(self) -> None:
        if self._program is None or not self._program.isLinked():
            return
        if self._mesh is None or self._mesh.n_faces == 0:
            self._n_verts = 0
            return

        m = self._mesh
        verts = m.vertices[m.faces]  # (n, 3, 3)
        pos = verts.reshape(-1, 3).astype(np.float32)
        norm = np.repeat(m.normals, 3, axis=0).astype(np.float32)
        data = np.hstack([pos, norm]).astype(np.float32).tobytes()

        self._vao = QOpenGLVertexArrayObject()
        self._vao.create()
        self._vao.bind()

        self._vbo = QOpenGLBuffer(QOpenGLBuffer.VertexBuffer)
        self._vbo.create()
        self._vbo.bind()
        self._vbo.allocate(data, len(data))

        stride = 6 * 4
        self._program.bind()
        loc = self._program.attributeLocation("aPos")
        self._program.enableAttributeArray(loc)
        self._program.setAttributeBuffer(loc, 0x1406, 0, 3, stride)
        loc = self._program.attributeLocation("aNormal")
        self._program.enableAttributeArray(loc)
        self._program.setAttributeBuffer(loc, 0x1406, 3 * 4, 3, stride)
        self._program.release()

        self._vao.release()
        self._vbo.release()
        self._n_verts = len(pos)

    def _matrix(self):
        import math

        s = self._scale * self._zoom
        rx = math.radians(self._rot_x)
        ry = math.radians(self._rot_y)
        cx, cy = math.cos(rx), math.sin(rx)
        cxx, cyy = math.cos(ry), math.sin(ry)
        # build rotation (Y then X)
        rot_y = np.array([[cxx, 0, cyy], [0, 1, 0], [-cyy, 0, cxx]])
        rot_x = np.array([[1, 0, 0], [0, cx, -cy], [0, cy, cx]])
        rot = rot_x @ rot_y
        model = np.eye(4, dtype=np.float32)
        model[:3, :3] = (rot * s).astype(np.float32)
        model[:3, 3] = (-rot @ self._center * s).astype(np.float32)

        # perspective projection
        aspect = max(self.width() / max(self.height(), 1), 0.1)
        fov = 45.0
        f = 1.0 / math.tan(math.radians(fov) / 2.0)
        near, far = 0.01, 100.0
        proj = np.zeros((4, 4), dtype=np.float32)
        proj[0, 0] = f / aspect
        proj[1, 1] = f
        proj[2, 2] = (far + near) / (near - far)
        proj[2, 3] = (2 * far * near) / (near - far)
        proj[3, 2] = -1.0

        mvp = (proj @ model).astype(np.float32)
        normal_mat = np.linalg.inv(model[:3, :3]).T.astype(np.float32)
        return model, proj, mvp, normal_mat

    def paintGL(self) -> None:
        from PySide6.QtGui import QMatrix3x3, QMatrix4x4, QOpenGLContext

        f = QOpenGLContext.currentContext().functions()
        f.glClearColor(0.078, 0.086, 0.122, 1.0)
        f.glClear(0x00004000 | 0x00000100)  # GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT
        f.glEnable(0x0B71)  # GL_DEPTH_TEST

        if self._n_verts == 0 or self._program is None:
            return

        model, proj, mvp, normal_mat = self._matrix()
        self._program.bind()
        loc_mvp = self._program.uniformLocation(b"uMVP")
        loc_model = self._program.uniformLocation(b"uModel")
        loc_normal = self._program.uniformLocation(b"uNormalMat")
        f.glUniformMatrix4fv(loc_mvp, 1, True, mvp.flatten().tolist())
        f.glUniformMatrix4fv(loc_model, 1, True, model.flatten().tolist())
        f.glUniformMatrix3fv(loc_normal, 1, True, normal_mat.flatten().tolist())
        self._program.setUniformValue("uLightDir", 0.5, 0.6, 1.0)
        self._program.setUniformValue("uBaseColor", *self._base_color)

        self._vao.bind()
        f.glDrawArrays(0x0004, 0, self._n_verts)  # GL_TRIANGLES
        self._vao.release()
        self._program.release()

    # ----------------------------------------------------------------- mouse
    def mousePressEvent(self, e: QMouseEvent) -> None:
        self._last = e.position()

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if e.buttons() & Qt.LeftButton:
            dx = e.position().x() - self._last.x()
            dy = e.position().y() - self._last.y()
            self._rot_y += dx * 0.5
            self._rot_x += dy * 0.5
            self._rot_x = max(-89.0, min(89.0, self._rot_x))
            self._last = e.position()
            self.update()
        elif e.buttons() & Qt.MiddleButton:
            dy = e.position().y() - self._last.y()
            self._zoom *= 1.0 + dy * 0.01
            self._zoom = max(0.1, min(20.0, self._zoom))
            self._last = e.position()
            self.update()

    def wheelEvent(self, e: QWheelEvent) -> None:
        self._zoom *= 1.0 + e.angleDelta().y() * 0.001
        self._zoom = max(0.1, min(20.0, self._zoom))
        self.update()
