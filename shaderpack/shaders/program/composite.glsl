// Water (refraction, absorption, reflections), SSR on smooth surfaces, fog, god rays.
#include "/lib/settings.glsl"
#include "/lib/uniforms.glsl"
#include "/lib/util.glsl"
#include "/lib/sky.glsl"
#include "/lib/shadows.glsl"
#include "/lib/pbr.glsl"
#include "/lib/ssr.glsl"

#ifdef VERTEX
out vec2 texcoord;
void main() {
    texcoord = gl_MultiTexCoord0.xy;
    gl_Position = ftransform();
}
#endif

#ifdef FRAGMENT
in vec2 texcoord;
layout(location = 0) out vec4 outColor;

const vec3 WATER_ABSORB = vec3(0.42, 0.075, 0.05);

vec3 waterScatter(float skyLight) {
    vec3 light = skyAmbientColor() * 1.2 + directLightColor() * 0.12;
    return vec3(0.03, 0.16, 0.19) * light * (0.15 + 0.85 * skyLight * skyLight);
}

vec3 reflection(vec3 vp, vec3 R, float skyLight, float dither, float rough) {
    vec3 Rw = mat3(gbufferModelViewInverse) * R;
    vec3 refl = skyWithClouds(Rw) * skyLight * skyLight + sunDisk(Rw) * skyLight * (1.0 - rough);
#ifdef SSR
    vec3 hit = raytrace(vp, R, dither, depthtex1);
    if (hit.z > 0.5) {
        vec3 h = textureLod(colortex0, hit.xy, rough * 4.0).rgb;
        refl = mix(refl, h, edgeFade(hit.xy));
    }
#endif
    return refl;
}

void main() {
    vec2 uv = texcoord;
    vec3 col = texture(colortex0, uv).rgb;
    float d0 = texture(depthtex0, uv).r;
    float d1 = texture(depthtex1, uv).r;
    vec3 vp0 = screenToView(vec3(uv, d0));
    vec3 V = -normalize(vp0);
    vec3 dirW = normalize(mat3(gbufferModelViewInverse) * vp0);
    float dither = ign(gl_FragCoord.xy);
    vec4 wdata = texture(colortex6, uv);
    bool water = wdata.b > 0.5 && d0 < d1 + 1e-6 && d0 < 1.0;

    if (water) {
        vec3 N = octDecode(wdata.rg);
        float skyLight = wdata.a;
        if (isEyeInWater == 0) {
            // refraction + absorption of what is behind the surface
            vec2 ruv = uv;
        #ifdef WATER_REFRACTION
            vec2 off = N.xy * 0.035 / max(1.0, -vp0.z * 0.08);
            if (texture(depthtex1, uv + off).r > d0) ruv = uv + off;
        #endif
            vec3 behind = texture(colortex0, ruv).rgb;
            float dr = texture(depthtex1, ruv).r;
            float dist = dr >= 1.0 ? 80.0 : length(screenToView(vec3(ruv, dr)) - vp0);
            vec3 trans = exp(-WATER_ABSORB * WATER_DENSITY * dist);
            col = behind * trans + waterScatter(skyLight) * (1.0 - exp(-dist * 0.3 * WATER_DENSITY));
        }
        // reflection
        vec3 R = reflect(-V, N);
        float F = fresnelSchlick(dot(N, V), vec3(0.02)).x;
        if (isEyeInWater == 1) F = max(F, smoothstep(0.35, 0.0, dot(N, V)));   // total internal reflection
        vec3 refl = reflection(vp0, R, isEyeInWater == 1 ? 0.0 : skyLight, dither, 0.0);
        col = mix(col, refl, F);
        // sun glint
        vec3 playerPos = mat3(gbufferModelViewInverse) * vp0 + gbufferModelViewInverse[3].xyz;
        vec3 sh = getShadow(playerPos, vec3(0.0, 1.0, 0.0), dither, 0.5);
        col += specularGGX(N, V, normalize(shadowLightPosition), 0.035, vec3(0.02)) * directLightColor() * sh;
    }
#ifdef SSR
    else if (d0 < 1.0) {
        vec4 spec = texture(colortex2, uv);
        vec4 alb = texture(colortex3, uv);
        int matId = int(alb.a * 255.0 + 0.5);
        float smoothness = spec.r;
        if (smoothness > SSR_THRESHOLD && matId != MAT_HAND && matId != MAT_NONE && d0 == d1) {
            vec4 nl = texture(colortex1, uv);
            vec3 N = octDecode(nl.rg);
            float f0raw = spec.g * 255.0;
            vec3 albedo = toLinear(alb.rgb);
            vec3 f0 = f0raw > 229.5 ? metalF0(int(f0raw + 0.5), albedo) : vec3(spec.g);
            float rough = sq(1.0 - smoothness);
            vec3 jitter = (vec3(hash12(gl_FragCoord.xy + frameTimeCounter), hash12(gl_FragCoord.yx * 1.7 + 3.1),
                                hash12(gl_FragCoord.xy * 0.7 - 5.3)) - 0.5) * rough * 0.5;
            vec3 R = normalize(reflect(-V, N) + jitter);
            if (dot(R, N) < 0.0) R = reflect(-V, N);
            vec3 F = fresnelSchlick(dot(N, V), f0);
            vec3 refl = reflection(vp0, R, nl.a, dither, rough);
            float w = smoothstep(SSR_THRESHOLD, SSR_THRESHOLD + 0.15, smoothness);
            col += refl * F * w;
        }
    }
#endif

    // ------------------------------------------------------------------ fog
    float dist = d0 >= 1.0 ? far * 2.0 : length(vp0);
    if (isEyeInWater == 1) {
        float skyEye = eyeBrightnessSmooth.y / 240.0;
        col = col * exp(-WATER_ABSORB * WATER_DENSITY * dist * 0.7) +
              waterScatter(skyEye) * (1.0 - exp(-dist * 0.12 * WATER_DENSITY));
    } else if (isEyeInWater == 2) {
        col = mix(col, vec3(2.0, 0.6, 0.1), 1.0 - exp(-dist * 1.2));
    } else if (isEyeInWater == 3) {
        col = mix(col, vec3(0.8, 0.9, 1.0), 1.0 - exp(-dist * 0.8));
    } else if (d0 < 1.0) {
    #if defined DIM_NETHER
        float fog = 1.0 - exp(-dist * 0.012 * FOG_DENSITY);
        col = mix(col, getSky(dirW), fog);
    #elif defined DIM_END
        float fog = 1.0 - exp(-dist * 0.004 * FOG_DENSITY);
        col = mix(col, getSky(dirW) * 1.5, fog);
    #else
        vec3 worldPos = mat3(gbufferModelViewInverse) * vp0 + cameraPosition;
        float heightF = exp(-max(worldPos.y - 62.0, 0.0) * 0.012);
        float density = 0.0012 * FOG_DENSITY * (1.0 + rainStrength * 6.0) * (0.35 + 0.65 * heightF);
        float fog = 1.0 - exp(-dist * density);
        float skyEye = smoothstep(0.0, 0.6, eyeBrightnessSmooth.y / 240.0);
        vec3 fogCol = getSky(normalize(vec3(dirW.x, max(dirW.y, 0.0) * 0.5 + 0.02, dirW.z)));
        fogCol = mix(fogCol * 0.15, fogCol, skyEye);
        col = mix(col, fogCol, fog);
    #endif
        // hide the edge of the render distance
        float border = smoothstep(far * 0.72, far, length(vp0.xz));
        col = mix(col, getSky(dirW), border);
    }
    col *= 1.0 - max(blindness, darknessFactor) * smoothstep(2.0, 12.0, dist);

    // ------------------------------------------------------------ god rays
#if defined GODRAYS && !defined DIM_NETHER && !defined DIM_END
    if (isEyeInWater == 0) {
        vec4 lp = gbufferProjection * vec4(shadowLightPosition, 1.0);
        if (lp.w > 0.0) {
            vec2 luv = lp.xy / lp.w * 0.5 + 0.5;
            vec2 stepv = (luv - uv) / 20.0;
            vec2 p = uv + stepv * dither;
            float acc = 0.0;
            for (int i = 0; i < 20; i++) {
                if (any(lessThan(p, vec2(0.0))) || any(greaterThan(p, vec2(1.0)))) break;
                acc += step(1.0, texture(depthtex0, p).r);
                p += stepv;
            }
            acc /= 20.0;
            float facing = pow(saturate(dot(normalize(vp0), normalize(shadowLightPosition))), 6.0);
            float skyEye = eyeBrightnessSmooth.y / 240.0;
            col += directLightColor() * acc * facing * GODRAYS_STRENGTH * 0.18 * skyEye * (1.0 - rainStrength);
        }
    }
#endif

    outColor = vec4(col, 1.0);
}
#endif
