from PIL import Image
import os

class ImageEngine:
    def process_image(self, input_path, target_format, output_dir=None, compression="Ninguno", log_callback=print):
         output_format = target_format.upper()
         ext = target_format.lower()
         if output_format == "JPG":
             output_format = "JPEG"
             
         base_name = os.path.splitext(os.path.basename(input_path))[0]
         if output_dir:
             output_path = os.path.join(output_dir, f"{base_name}_compressed.{ext}")
         else:
             output_path = os.path.splitext(input_path)[0] + f"_compressed.{ext}"
         
         # Ajustar calidad según la compresión
         quality = 90
         if compression == "Media (Buena Calidad)":
             quality = 70
         elif compression == "Alta (Para Redes Sociales)":
             quality = 50
         elif compression == "Extrema":
             quality = 30
         
         try:
             log_callback(f"[IMAGEN] Comprimiendo {os.path.basename(input_path)} a {target_format} (Calidad: {quality}%)...")
             with Image.open(input_path) as img:
                 # Quitar canal alfa si convertimos a formatos que no lo soportan (JPEG, BMP)
                 if img.mode in ("RGBA", "P") and output_format in ["JPEG", "BMP"]:
                     img = img.convert("RGB")
                 
                 if output_format in ["JPEG", "WEBP"]:
                     img.save(output_path, output_format, quality=quality)
                 elif output_format == "PNG":
                     compress_level = 6
                     if compression == "Media (Buena Calidad)":
                         compress_level = 7
                     elif compression == "Alta (Para Redes Sociales)":
                         compress_level = 8
                     elif compression == "Extrema":
                         compress_level = 9
                     
                     if compression == "Extrema" and img.mode in ("RGB", "RGBA"):
                         try:
                             img = img.quantize(colors=256)
                         except Exception:
                             pass
                     img.save(output_path, output_format, optimize=True, compress_level=compress_level)
                 else:
                     img.save(output_path, output_format)
                     
             if os.path.exists(output_path):
                 orig_size = os.path.getsize(input_path)
                 comp_size = os.path.getsize(output_path)
                 if comp_size >= orig_size:
                     import shutil
                     try:
                         shutil.copy2(input_path, output_path)
                         log_callback(f"[IMAGEN] El archivo original ya estaba óptimamente comprimido. Se conservó el tamaño original.")
                     except Exception:
                         pass
             log_callback(f"[Éxito] Generado: {os.path.basename(output_path)}")
             return output_path
         except Exception as e:
             log_callback(f"[Error] Falló al comprimir imagen: {str(e)}")
             return None
