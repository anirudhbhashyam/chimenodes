#version 330 core
// chimenodes fullscreen vertex shader (shared by every post pass).
// Attribute  : location 0  `position`  vec2 in clip space; draw a quad of
//              (-1,-1) (1,-1) (-1,1) (1,1) as a triangle strip / 2 triangles.
// Varying    : `vUV` (vec2, 0..1) texture coordinate, y up (GL convention).
// No uniforms.
layout(location = 0) in vec2 position;
out vec2 vUV;
void main()
{
    vUV = position * 0.5 + 0.5;
    gl_Position = vec4(position, 0.0, 1.0);
}
