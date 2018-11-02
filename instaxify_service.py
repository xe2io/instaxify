from http.server import HTTPServer, BaseHTTPRequestHandler
import ssl
import subprocess
import base64
import cgi
# Determine uploaded file mime-type
import magic
import io

# For ICC profile conversion
from PIL import Image
from PIL import ImageCms
from PIL import ImageFilter

# Redirect stderr to stdout for running in Docker container TODO: fix logging
import sys
sys.stderr = sys.stdout

class InstaxConvert(object):
    def __init__(self):
        # TODO: constructor?
        input_profile = "calibration/sRGB.icm"
        proof_profile = "calibration/instax-sp1_00.icc"
        self.max_dim = 640
        self.quality = 100

        # Best visually from experimentation
        self.r = 0.6
        self.p = 200
        self.t = 0

        # Create ICC transform, save for reuse
        self.proof_xform = ImageCms.buildTransform(proof_profile, input_profile, "RGB", "RGB")

    def convert(self, img_byte):
        payload_bytes = io.BytesIO(img_byte)
        im_orig = Image.open(payload_bytes)

        # Calculate resized image size, scale by longest edge
        resize_ratio = max(im_orig.size)/self.max_dim
        resize_dim = (int(d / resize_ratio) for d in im_orig.size)

        # Resize
        im = im_orig.resize(resize_dim, resample=Image.LANCZOS)
        # Free memory from original image read
        del im_orig
        payload_bytes.close()

        # Save to byte array for output; this is freed by the caller
        output_img = io.BytesIO()
        im_sharpen = im.filter(ImageFilter.UnsharpMask(radius=self.r, percent=self.p, threshold=self.t))
        del im
        
        # Convert ICC profile
        ImageCms.applyTransform(im_sharpen, self.proof_xform, inPlace=True)

        im_sharpen.save(output_img, format='JPEG', quality=self.quality)
        del im_sharpen

        return output_img


# TODO: Hold onto this since we create a global xform profile
print("Creating ICC conversion profile...")
instax = InstaxConvert()


class InstaxifyHTTPRequestHandler(BaseHTTPRequestHandler):
    # POST field containing file contents
    image_payload_field = "f"

    # Maximum acceptable payload size = 15MB (allow for full-size jpg, but ideally would be downsized/cropped already)
    max_payload_size = 15 * 1024 * 1024

    def do_AUTHHEAD(self):
        self.send_response(401)
        #self.send_header('WWW-Authenticate', 'Basic realm=\"Give me scratches?\"')
        self.send_header('WWW-Authenticate', 'Basic')
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b'Unauthorized.')

    def do_GET(self):
        global key
        if self.headers.get('Authorization') == None:
            self.do_AUTHHEAD()
            pass
        elif self.headers.get('Authorization') == 'Basic '+str(key):
            self.show_get_form()
            pass
        else:
            self.do_AUTHHEAD()
            pass

    def do_POST(self):
        global key
        if self.headers.get('Authorization') == None:
            self.do_AUTHHEAD()
            pass
        elif self.headers.get('Authorization') == 'Basic '+str(key):
            self.handle_post_data()
            pass
        else:
            self.do_AUTHHEAD()
            pass

    def handle_post_data(self):
        # Don't accept large payloads; doesn't handle case when clients spoof this
        if int(self.headers['Content-Length']) > InstaxifyHTTPRequestHandler.max_payload_size:
            self.send_error(413, 'Image is too large.') 
            return
        # File uploads should have content-type of multipart/form-data
        if not self.headers['Content-Type'].startswith('multipart/form-data'):
            # Send error message
            self.send_error(400, 'Invalid request.')
            return

        # Extract file from payload, check that image is valid
        form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={
            'REQUEST_METHOD': 'POST', 
            'CONTENT_TYPE': self.headers['Content-Type']}
        )
        
        try:
            file_data = form[InstaxifyHTTPRequestHandler.image_payload_field].file.read()
           
            # Process image, return to client as image
            try:
                # Early detection of non-image (pythonic way would to try to parse and throw exception)
                if not magic.from_buffer(file_data, mime=True).startswith('image/'):
                    raise TypeError

                # should automatically call resp_bytes.close() to free BytesIO object when completed
                resp_bytes = instax.convert(file_data)
                resp_body = resp_bytes.getvalue()
                resp_type = magic.from_buffer(resp_body, mime=True);

                # Have a valid response (hopefully an image)
                self.send_response(200)
                self.send_header('Content-Type', resp_type)
                self.send_header('Content-Length', len(resp_body))
                self.end_headers()
                self.wfile.write(resp_body)
                del resp_body
                resp_bytes.close()
                
            except (IOError, TypeError):
                self.send_error(415, 'Invalid image format.')
                return
            finally:
                del file_data

        except KeyError:
            # Field image_payload_field doesn't exist in POST body
            self.send_error(400, 'No image specified.')
            return
        finally:
            # explicitly free memory
            del form

    def send_error(self, http_code, message):
        # Assume no responses have been sent
        self.send_response(http_code)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.end_headers()
        self.wfile.write(bytes(message, 'utf-8'))

    def show_get_form(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(b'''
        <form action="/" method="post" enctype="multipart/form-data">
            <input type="file" name="f" value="" />
            <input type="submit" value="Convert" />
        </form>
        ''')



httpd = HTTPServer(('', 8443), InstaxifyHTTPRequestHandler)
# TODO: don't hardcode
key = base64.b64encode(b"instax:").decode('ascii')

httpd.socket = ssl.wrap_socket (httpd.socket, 
        keyfile="cert/cert.key", 
        certfile="cert/cert.crt", server_side=True)

print("Starting conversion service.")

httpd.serve_forever()
