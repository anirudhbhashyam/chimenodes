#version 330 core
// Dual-Kawase 5-tap downsample (centre*4 + 4 diagonal) / 8.
// Textures : uSrc (sampler2D, higher-res level)
// Uniforms : uOutSize (vec2, target size px), uOffset (float, tap offset in src texels, ~1.0)
uniform sampler2D uSrc;
uniform vec2 uOutSize;
uniform float uOffset;
out vec4 fragColor;

void main() {
    vec2 uv = gl_FragCoord.xy / uOutSize;
    vec2 h = 0.5 / uOutSize * uOffset;     // half a destination texel
    vec3 s = texture(uSrc, uv).rgb * 4.0;
    s += texture(uSrc, uv + vec2(-h.x, -h.y)).rgb;
    s += texture(uSrc, uv + vec2( h.x, -h.y)).rgb;
    s += texture(uSrc, uv + vec2(-h.x,  h.y)).rgb;
    s += texture(uSrc, uv + vec2( h.x,  h.y)).rgb;
    fragColor = vec4(s * 0.125, 1.0);
}
