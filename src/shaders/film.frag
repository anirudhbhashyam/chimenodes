#version 330 core
// Film effects on LDR (post-tonemap): vignette (smoothstep^2), hash grain, chromatic aberration.
// Textures : uColor (sampler2D LDR colour)
// Uniforms : uVignette (float 0..1), uGrain (float 0..1), uChroma (float, 0..~0.005 fraction of
//            width, 0 = off), uSeed (float, vary per frame; 0 for stills), uGrainCell (float px,
//            ~ max(1, height/1080))
uniform sampler2D uColor;
uniform float uVignette;
uniform float uGrain;
uniform float uChroma;
uniform float uSeed;
uniform float uGrainCell;
out vec4 fragColor;

float hash12(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

void main() {
    vec2 size = vec2(textureSize(uColor, 0));
    vec2 uv = gl_FragCoord.xy / size;
    vec2 cc = uv - 0.5;
    vec4 base = texture(uColor, uv);
    vec3 col = base.rgb;
    if (uChroma > 0.0) {
        vec2 o = cc * uChroma * 2.0;
        col.r = texture(uColor, uv + o).r;
        col.b = texture(uColor, uv - o).b;
    }
    if (uVignette > 0.0) {
        vec2 q = cc * vec2(size.x / size.y, 1.0);
        float r = length(q) / 0.7071 / (size.x / size.y > 1.0 ? 1.0 : 1.0);
        float v = smoothstep(0.35, 1.2, r);
        v *= v;
        col *= 1.0 - uVignette * v;
    }
    if (uGrain > 0.0) {
        vec2 cell = floor(gl_FragCoord.xy / max(uGrainCell, 1.0));
        float n = hash12(cell + uSeed * 17.0) - 0.5;
        float lum = dot(col, vec3(0.2126, 0.7152, 0.0722));
        col += n * uGrain * 0.12 * (1.0 - 0.5 * lum);   // stronger in shadows
    }
    fragColor = vec4(col, base.a);
}
