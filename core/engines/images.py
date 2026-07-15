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
                 else:
                     img.save(output_path, output_format)
                     
             log_callback(f"[Éxito] Generado: {os.path.basename(output_path)}")
             return output_path
         except Exception as e:
             log_callback(f"[Error] Falló al comprimir imagen: {str(e)}")
             return None
