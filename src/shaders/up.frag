#version 330 core
// Dual-Kawase 8-tap tent upsample, optionally adding a base texture and an emission texture.
//   out = uBase*uBaseWeight + uAdd*uAddWeight + tent(uSrc)*uSrcWeight
// Textures : uSrc (sampler2D, lower-res level), uBase (sampler2D, same res as target; bound to
//            any texture when uBaseWeight == 0), uAdd (sampler2D full-res emission; same rule)
// Uniforms : uOutSize (vec2), uOffset (float ~1.0), uSrcWeight, uBaseWeight, uAddWeight (float)
uniform sampler2D uSrc;
uniform sampler2D uBase;
uniform sampler2D uAdd;
uniform vec2 uOutSize;
uniform float uOffset;
uniform float uSrcWeight;
uniform float uBaseWeight;
uniform float uAddWeight;
out vec4 fragColor;

void main() {
    vec2 uv = gl_FragCoord.xy / uOutSize;
    vec2 h = 0.5 / vec2(textureSize(uSrc, 0)) * uOffset;
    vec3 s = vec3(0.0);
    s += texture(uSrc, uv + vec2(-2.0 * h.x, 0.0)).rgb;
    s += texture(uSrc, uv + vec2(-h.x,  h.y)).rgb * 2.0;
    s += texture(uSrc, uv + vec2(0.0,  2.0 * h.y)).rgb;
    s += texture(uSrc, uv + vec2( h.x,  h.y)).rgb * 2.0;
    s += texture(uSrc, uv + vec2( 2.0 * h.x, 0.0)).rgb;
    s += texture(uSrc, uv + vec2( h.x, -h.y)).rgb * 2.0;
    s += texture(uSrc, uv + vec2(0.0, -2.0 * h.y)).rgb;
    s += texture(uSrc, uv + vec2(-h.x, -h.y)).rgb * 2.0;
    s /= 12.0;
    vec4 base = texture(uBase, uv);
    vec3 col = s * uSrcWeight;
    if (uBaseWeight != 0.0) col += base.rgb * uBaseWeight;
    if (uAddWeight != 0.0) col += texture(uAdd, uv).rgb * uAddWeight;
    fragColor = vec4(col, uBaseWeight != 0.0 ? base.a : 1.0);
}
