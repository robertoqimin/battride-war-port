/* Probe the host Vulkan loader/driver and the current SDL display session.
 * No shaders, game data or controller events are involved. */
#include <SDL.h>
#include <SDL_vulkan.h>
#include <vulkan/vulkan.h>
#include <stdio.h>
#include <stdlib.h>
int main(void) {
    SDL_Window *window = NULL; VkInstance instance = VK_NULL_HANDLE;
    VkSurfaceKHR surface = VK_NULL_HANDLE; int result = 1;
    if (SDL_Init(SDL_INIT_VIDEO)) { fprintf(stderr,"SDL video: %s\n",SDL_GetError()); return 1; }
    window=SDL_CreateWindow("Vulkan compatibility check",SDL_WINDOWPOS_UNDEFINED,SDL_WINDOWPOS_UNDEFINED,
                            64,64,SDL_WINDOW_HIDDEN|SDL_WINDOW_VULKAN);
    if(!window){fprintf(stderr,"SDL Vulkan window: %s\n",SDL_GetError());goto done;}
    unsigned count=0; const char *extensions[32];
    if(!SDL_Vulkan_GetInstanceExtensions(window,&count,NULL)||count>32||
       !SDL_Vulkan_GetInstanceExtensions(window,&count,extensions)) {fprintf(stderr,"SDL extensions: %s\n",SDL_GetError());goto done;}
    VkApplicationInfo app={.sType=VK_STRUCTURE_TYPE_APPLICATION_INFO,.pApplicationName="Battride compatibility check",.apiVersion=VK_API_VERSION_1_0};
    VkInstanceCreateInfo ci={.sType=VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,.pApplicationInfo=&app,.enabledExtensionCount=count,.ppEnabledExtensionNames=extensions};
    VkResult error=vkCreateInstance(&ci,NULL,&instance);
    if(error){fprintf(stderr,"vkCreateInstance failed: %d. Check the host Vulkan driver and VK_LOADER_DEBUG output.\n",error);goto done;}
    if(!SDL_Vulkan_CreateSurface(window,instance,&surface)){fprintf(stderr,"Vulkan surface: %s\n",SDL_GetError());goto done;}
    uint32_t n=0;vkEnumeratePhysicalDevices(instance,&n,NULL);
    VkPhysicalDevice *devices=calloc(n?n:1,sizeof(*devices));
    if(!devices)goto done;
    if(vkEnumeratePhysicalDevices(instance,&n,devices)!=VK_SUCCESS){free(devices);goto done;}
    for(uint32_t i=0;i<n;i++) {
        VkPhysicalDeviceProperties props;VkPhysicalDeviceFeatures features;
        vkGetPhysicalDeviceProperties(devices[i],&props);vkGetPhysicalDeviceFeatures(devices[i],&features);
        printf("GPU: %s (Vulkan %u.%u.%u), BC textures: %s\n",props.deviceName,
               VK_VERSION_MAJOR(props.apiVersion),VK_VERSION_MINOR(props.apiVersion),VK_VERSION_PATCH(props.apiVersion),features.textureCompressionBC?"yes":"no");
        if(!features.textureCompressionBC)continue;
        uint32_t queues=0;vkGetPhysicalDeviceQueueFamilyProperties(devices[i],&queues,NULL);
        VkQueueFamilyProperties *q=calloc(queues?queues:1,sizeof(*q));if(!q)continue;
        vkGetPhysicalDeviceQueueFamilyProperties(devices[i],&queues,q);
        for(uint32_t j=0;j<queues;j++) {
            VkBool32 present=VK_FALSE;vkGetPhysicalDeviceSurfaceSupportKHR(devices[i],j,surface,&present);
            if(!(q[j].queueFlags&VK_QUEUE_GRAPHICS_BIT)||!present)continue;
            float priority=1;VkDevice device=VK_NULL_HANDLE;const char *swapchain=VK_KHR_SWAPCHAIN_EXTENSION_NAME;
            VkDeviceQueueCreateInfo qi={.sType=VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO,.queueFamilyIndex=j,.queueCount=1,.pQueuePriorities=&priority};
            VkPhysicalDeviceFeatures required={.textureCompressionBC=VK_TRUE};
            VkDeviceCreateInfo di={.sType=VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO,.queueCreateInfoCount=1,.pQueueCreateInfos=&qi,.enabledExtensionCount=1,.ppEnabledExtensionNames=&swapchain,.pEnabledFeatures=&required};
            error=vkCreateDevice(devices[i],&di,NULL,&device);
            if(!error){vkDestroyDevice(device,NULL);result=0;break;}
            fprintf(stderr,"GPU device creation failed: %d\n",error);
        }
        free(q);
    }
    free(devices);
    if(result)fprintf(stderr,"No GPU with Vulkan graphics/presentation, swapchain and BC textures could be initialized.\n");
    else puts("Vulkan window/device check passed.");
done:
    if(surface)vkDestroySurfaceKHR(instance,surface,NULL);
    if(instance)vkDestroyInstance(instance,NULL);
    if(window)SDL_DestroyWindow(window);
    SDL_Quit();return result;
}
