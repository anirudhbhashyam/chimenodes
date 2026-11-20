#version 330 core
// chimenodes "MN look" composite pass: AO multiplied into albedo (SSAO-lite,
// emulates Blender ColorAO) and a Fresnel rim term, both from depth only.
//
// Textures (sampler2D):
//   uColor    scene colour (RGBA16F, display-referred as ChimeraX renders it)
//   uDepth    scene depth texture (0..1, default glDepthRange)
// Uniforms:
//   vec2  uTexel     1/width, 1/height of the render target
//   float uNear, uFar  camera clip distances (positive, scene units)
//   int   uOrtho     1 for orthographic camera, 0 for perspective
//   vec2  uInvProj   (1/P[0][0], 1/P[1][1]) of the projection matrix
//   float uAO        AO strength 0..1 (params.ao)
//   float uAORadius  AO radius in scene units (params.ao_radius * scene_radius)
//   float uRim       rim strength 0..1 (params.rim)
// Input varying: vUV (from fullscreen.vert). Output: fragColor (alpha kept).
uniform sampler2D uColor;
uniform sampler2D uDepth;
uniform vec2  uTexel;
uniform float uNear;
uniform float uFar;
uniform int   uOrtho;
uniform vec2  uInvProj;
uniform float uAO;
uniform float uAORadius;
uniform float uRim;

in vec2 vUV;
out vec4 fragColor;

const int N_SAMPLES = 16;

vec3 toLinear(vec3 c)
{
    c = max(c, vec3(0.0));
    return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(vec3(0.04045), c));
}
vec3 toSRGB(vec3 c)
{
    c = max(c, vec3(0.0));
    return mix(c * 12.92, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, step(vec3(0.0031308), c));
}

float linearDepth(float d)
{
    float z = d * 2.0 - 1.0;
    if (uOrtho == 1)
        return (z * (uFar - uNear) + uFar + uNear) * 0.5;
    return 2.0 * uNear * uFar / (uFar + uNear - z * (uFar - uNear));
}

// View-space position (camera looks down -z). Returns w=0 for background.
vec4 viewPos(vec2 uv)
{
    float raw = texture(uDepth, uv).r;
    if (raw >= 1.0) return vec4(0.0);
    float d = linearDepth(raw);
    vec2 ndc = uv * 2.0 - 1.0;
    vec2 xy = ndc * uInvProj * ((uOrtho == 1) ? 1.0 : d);
    return vec4(xy, -d, 1.0);
}

float ign(vec2 p)  // interleaved gradient noise
{
    return fract(52.9829189 * fract(dot(p, vec2(0.06711056, 0.00583715))));
}

void main()
{
    vec4 col = texture(uColor, vUV);
    if (uAO <= 0.0 && uRim <= 0.0) { fragColor = col; return; }
    vec4 pc = viewPos(vUV);
    if (pc.w == 0.0) { fragColor = col; return; }
    vec3 P = pc.xyz;

    // normal from depth, choosing the smaller depth difference per axis
    vec4 l = viewPos(vUV - vec2(uTexel.x, 0.0));
    vec4 r = viewPos(vUV + vec2(uTexel.x, 0.0));
    vec4 d = viewPos(vUV - vec2(0.0, uTexel.y));
    vec4 u = viewPos(vUV + vec2(0.0, uTexel.y));
    vec3 dx = P - P, dy = P - P;
    bool okx = (l.w > 0.0) || (r.w > 0.0);
    bool oky = (d.w > 0.0) || (u.w > 0.0);
    if (l.w > 0.0 && (r.w == 0.0 || abs(l.z - P.z) < abs(r.z - P.z))) dx = P - l.xyz;
    else if (r.w > 0.0) dx = r.xyz - P;
    if (d.w > 0.0 && (u.w == 0.0 || abs(d.z - P.z) < abs(u.z - P.z))) dy = P - d.xyz;
    else if (u.w > 0.0) dy = u.xyz - P;
    vec3 n = vec3(0.0, 0.0, 1.0);
    if (okx && oky) {
        vec3 c = cross(dx, dy);
        if (dot(c, c) > 1e-20) n = normalize(c);
        if (dot(n, -P) < 0.0) n = -n;
    }

    float f = 1.0;
    if (uAO > 0.0) {
        float H = 1.0 / uTexel.y;
        float rpx;
        if (uOrtho == 1) rpx = uAORadius / uInvProj.y * 0.5 * H;
        else             rpx = uAORadius / (-P.z * uInvProj.y) * 0.5 * H;
        rpx = clamp(rpx, 2.0, 0.25 * H);
        float rot = ign(gl_FragCoord.xy) * 6.2831853;
        float sum = 0.0;
        for (int i = 0; i < N_SAMPLES; ++i) {
            float t = (float(i) + 0.5) / float(N_SAMPLES);
            float a = float(i) * 2.39996323 + rot;
            vec2 off = vec2(cos(a), sin(a)) * sqrt(t) * rpx * uTexel;
            vec4 s = viewPos(vUV + off);
            if (s.w == 0.0) continue;
            vec3 v = s.xyz - P;
            float dist = length(v);
            if (dist < 1e-6) continue;
            float occ = max(dot(n, v) / dist - 0.1, 0.0);
            float w = clamp(1.0 - dist / (1.5 * uAORadius), 0.0, 1.0);
            sum += occ * w;
        }
        float ao = clamp(1.0 - 1.6 * sum / float(N_SAMPLES), 0.0, 1.0);
        f = mix(1.0, ao, uAO);
    }
    vec3 lin = toLinear(col.rgb) * f;
    vec3 outc = toSRGB(lin);
    if (uRim > 0.0) {
        float ndv = clamp(dot(n, normalize(-P)), 0.0, 1.0);
        float fres = pow(1.0 - ndv, 3.0);
        outc += uRim * fres * (0.2 + 0.4 * outc) * f;
    }
    fragColor = vec4(outc, col.a);
}
