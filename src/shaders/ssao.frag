#version 330 core
// Reusable half-res hemisphere-ish SSAO from depth only, plus bilateral blur. Optional; B may use it.
// Output: AO in .r (1 = unoccluded). uMode selects the stage.
// Textures : uDepth (sampler2D); uAO (sampler2D, only for uMode==1 blur input)
// Uniforms : uMode (int 0 = ssao, 1 = bilateral blur; blur direction uDir),
//            uOutSize (vec2), uNear, uFar (float), uOrtho (int),
//            uTanHalf (vec2: tan(fov/2)*aspect, tan(fov/2)), uRadius (float, scene units),
//            uStrength (float), uSamples (int 8..24), uDir (vec2 blur axis in texels, mode 1)
uniform sampler2D uDepth;
uniform sampler2D uAO;
uniform int uMode;
uniform vec2 uOutSize;
uniform float uNear;
uniform float uFar;
uniform int uOrtho;
uniform vec2 uTanHalf;
uniform float uRadius;
uniform float uStrength;
uniform int uSamples;
uniform vec2 uDir;
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
float hash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }

void main() {
    vec2 uv = gl_FragCoord.xy / uOutSize;
    if (uMode == 1) {
        float cd = lin(texture(uDepth, uv).r);
        float sum = 0.0, ws = 0.0;
        for (int i = -3; i <= 3; ++i) {
            vec2 suv = uv + uDir * float(i) / uOutSize;
            float sd = lin(texture(uDepth, suv).r);
            float w = exp(-float(i * i) / 8.0) * exp(-abs(sd - cd) / (0.05 * uRadius + 1e-4));
            sum += texture(uAO, suv).r * w; ws += w;
        }
        fragColor = vec4(vec3(sum / max(ws, 1e-5)), 1.0);
        return;
    }
    float d0 = texture(uDepth, uv).r;
    if (d0 >= 1.0) { fragColor = vec4(1.0); return; }
    float z0 = lin(d0);
    vec3 p = viewPos(uv, z0);
    // normal from depth derivatives
    vec2 px = 1.0 / uOutSize;
    vec3 pr = viewPos(uv + vec2(px.x, 0.0), lin(texture(uDepth, uv + vec2(px.x, 0.0)).r));
    vec3 pu = viewPos(uv + vec2(0.0, px.y), lin(texture(uDepth, uv + vec2(0.0, px.y)).r));
    vec3 n = normalize(cross(pr - p, pu - p));
    if (n.z < 0.0) n = -n;   // face the camera (+z in view space)
    float rnd = hash(gl_FragCoord.xy) * 6.2831853;
    float occ = 0.0;
    for (int i = 0; i < uSamples; ++i) {
        float fi = (float(i) + 0.5) / float(uSamples);
        float a = rnd + float(i) * 2.39996323;
        float r = mix(0.1, 1.0, fi * fi) * uRadius;
        float h = sqrt(1.0 - fi * 0.7);
        vec3 dir = normalize(vec3(cos(a) * sqrt(1.0 - h * h), sin(a) * sqrt(1.0 - h * h), h));
        // orient into hemisphere about n
        vec3 t = normalize(cross(abs(n.x) > 0.5 ? vec3(0, 1, 0) : vec3(1, 0, 0), n));
        vec3 b = cross(n, t);
        vec3 sp = p + (t * dir.x + b * dir.y + n * dir.z) * r;
        vec2 suv;
        if (uOrtho != 0) suv = (sp.xy / uTanHalf) * 0.5 + 0.5;
        else suv = (sp.xy / (uTanHalf * max(-sp.z, 1e-4))) * 0.5 + 0.5;
        float sz = lin(texture(uDepth, suv).r);
        float diff = (-sp.z) - sz;                         // >0: sample is behind surface
        float range = smoothstep(0.0, 1.0, uRadius / max(abs(z0 - sz), 1e-4));
        occ += (diff > 0.02 * uRadius ? 1.0 : 0.0) * range;
    }
    float ao = 1.0 - uStrength * occ / float(uSamples);
    fragColor = vec4(vec3(clamp(ao, 0.0, 1.0)), 1.0);
}
