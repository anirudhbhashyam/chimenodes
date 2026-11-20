#version 330 core
// Glow light: glowing atoms act as point lights tinting nearby surfaces (screen space, depth only).
// Textures : uColor (scene), uDepth (window depth), uEmission (glow-only colours / uGain; bound to
//            uColor when uHasEmission == 0)
// Uniforms : uNear, uFar, uOrtho (int), uTanHalf (vec2), uOutSize (vec2),
//            uLightPos[32] (view space), uLightCol[32] (linear rgb, strength folded in), uCount,
//            uStrength, uRadius (scene units), uGain, uHasEmission
uniform sampler2D uColor;
uniform sampler2D uDepth;
uniform sampler2D uEmission;
uniform float uNear;
uniform float uFar;
uniform int uOrtho;
uniform vec2 uTanHalf;
uniform vec2 uOutSize;
uniform vec3 uLightPos[32];
uniform vec3 uLightCol[32];
uniform int uCount;
uniform float uStrength;
uniform float uRadius;
uniform float uGain;
uniform int uHasEmission;
out vec4 fragColor;

float lin(float d) {
    if (uOrtho != 0) return uNear + d * (uFar - uNear);
    return uNear * uFar / max(uFar - d * (uFar - uNear), 1e-6);
}
vec3 viewPos(vec2 uv, float z) {
    vec2 ndc = uv * 2.0 - 1.0;
    if (uOrtho != 0) return vec3(ndc * uTanHalf, -z);
    return vec3(ndc * uTanHalf * z, -z);
}
float luma(vec3 c) { return dot(c, vec3(0.2126, 0.7152, 0.0722)); }

void main() {
    vec2 uv = gl_FragCoord.xy / uOutSize;
    vec4 base = texture(uColor, uv);
    float d0 = texture(uDepth, uv).r;
    if (d0 >= 1.0 || uCount <= 0) { fragColor = base; return; }
    vec3 p = viewPos(uv, lin(d0));
    vec2 px = 1.0 / uOutSize;
    vec2 uvr = uv + vec2(px.x, 0.0);
    vec2 uvu = uv + vec2(0.0, px.y);
    vec3 pr = viewPos(uvr, lin(texture(uDepth, uvr).r));
    vec3 pu = viewPos(uvu, lin(texture(uDepth, uvu).r));
    vec3 n = cross(pr - p, pu - p);
    float nl = length(n);
    n = nl > 1e-12 ? n / nl : vec3(0.0, 0.0, 1.0);
    if (n.z < 0.0) n = -n;   // face the camera

    float R = max(uRadius, 1e-3);
    float R3 = 3.0 * R;
    vec3 light = vec3(0.0);
    for (int i = 0; i < 32; ++i) {
        if (i >= uCount) break;
        vec3 lv = uLightPos[i] - p;
        float d = length(lv);
        if (d >= R3) continue;
        float q = d / R;
        float fall = 1.0 / ((1.0 + q * q) * (1.0 + q * q));   // steeper than inverse-square: stays local
        float edge = 1.0 - smoothstep(2.0, 3.0, q);       // smooth to zero at 3R
        // wrap / two-sided: translucent depth means the light is often behind the visible wall
        float ndl = mix(0.35, 1.0, 0.5 + 0.5 * dot(n, lv / max(d, 1e-5)));
        light += uLightCol[i] * (fall * edge * ndl);
    }

    float recv = 1.0;
    if (uHasEmission != 0) {
        vec3 e = texture(uEmission, uv).rgb * uGain;
        recv = 1.0 - clamp(luma(e) * 2.0, 0.0, 1.0);
    }
    float alb = 0.2 + 0.8 * clamp(luma(base.rgb), 0.0, 1.0);
    vec3 add = light * (uStrength * recv * alb);
    fragColor = vec4(base.rgb + add, base.a);
}
