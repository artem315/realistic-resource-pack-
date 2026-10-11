// Sky, sun and clouds behind the opaque geometry.

/*
const int colortex0Format = RGBA16F;
const int colortex1Format = RGBA16;
const int colortex2Format = RGBA8;
const int colortex3Format = RGBA8;
const int colortex6Format = RGBA16;
const bool colortex0Clear = true;
const bool colortex1Clear = true;
const bool colortex2Clear = true;
const bool colortex3Clear = true;
const bool colortex6Clear = true;
const vec4 colortex0ClearColor = vec4(0.0, 0.0, 0.0, 0.0);
const vec4 colortex1ClearColor = vec4(0.0, 0.0, 0.0, 0.0);
const vec4 colortex2ClearColor = vec4(0.0, 0.0, 0.0, 0.0);
const vec4 colortex3ClearColor = vec4(0.0, 0.0, 0.0, 0.0);
const vec4 colortex6ClearColor = vec4(0.0, 0.0, 0.0, 0.0);
*/
#include "/lib/settings.glsl"
#include "/lib/uniforms.glsl"
#include "/lib/util.glsl"
#include "/lib/sky.glsl"

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

void main() {
    vec3 col = texture(colortex0, texcoord).rgb;
    float d = texture(depthtex0, texcoord).r;
    if (d >= 1.0) {
        vec3 vp = screenToView(vec3(texcoord, 1.0));
        vec3 dir = normalize(mat3(gbufferModelViewInverse) * vp);
        vec3 sky = getSky(dir);
        float cloudA = 0.0;
    #if defined CLOUDS && !defined DIM_NETHER && !defined DIM_END
        vec4 cl = clouds(dir);
        cloudA = cl.a;
    #endif
        // stars and the moon were written to colortex0 by the sky programs
        sky += (col + sunDisk(dir)) * (1.0 - cloudA);
    #if defined CLOUDS && !defined DIM_NETHER && !defined DIM_END
        sky = mix(sky, cl.rgb, cl.a);
    #endif
        col = sky;
    }
    outColor = vec4(col, 1.0);
}
#endif
