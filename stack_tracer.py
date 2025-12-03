import functools
import time
import sys
import io

# --- The Output Interceptor ---
class IndentedStdout:
    """
    A file-like object that intercepts print statements and 
    adds the current indentation level to them.
    """
    def __init__(self, tracer, original_stdout):
        self.tracer = tracer
        self.original = original_stdout
        # logic to track if we are at the start of a new line
        self.at_line_start = True

    def write(self, text):
        if not text:
            return

        # Prepare the indentation string (e.g. "|   |   ")
        # We add one extra pipe for the current function's body
        indent = "|   " * (self.tracer.depth) + "| "
        
        # We process the text to inject indentation after every newline
        # This handles cases like print("Line1\nLine2")
        for char in text:
            if self.at_line_start:
                self.original.write(indent)
                self.at_line_start = False
            
            self.original.write(char)
            
            if char == '\n':
                self.at_line_start = True

    def flush(self):
        self.original.flush()

# --- The Main Tracer ---
class StackTracer:
    def __init__(self, show_timing=True, show_input=True, show_output=True, output_file=None):
        self.depth = 0
        self.show_timing = show_timing
        self.show_input = show_input
        self.show_output = show_output
        self._output_file_path = output_file
        self._file_handle = None
        
        # We keep track of the original stdout so we can restore it later
        self.original_stdout = sys.stdout
        # We create our interceptor, but don't install it yet
        self.interceptor = IndentedStdout(self, self.original_stdout)

    def _log(self, message):
        """Writes to the real stdout (bypassing the interceptor for tracer logs)"""
        # If we are logging to a file, write there
        if self._file_handle:
            self._file_handle.write(message + "\n")
            self._file_handle.flush()
        else:
            # If logging to console, write directly to original stdout
            # to avoid double-indenting our own logs
            self.original_stdout.write(message + "\n")
            self.original_stdout.flush()

    def __call__(self, func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 1. SETUP: Redirect stdout if this is the top-level call
            previous_stdout = sys.stdout
            if self._output_file_path and self._file_handle is None:
                 self._file_handle = open(self._output_file_path, 'w', encoding='utf-8')
            
            # Only hijack stdout if we haven't already
            if not isinstance(sys.stdout, IndentedStdout) and not self._file_handle:
                sys.stdout = self.interceptor

            # 2. VISUALS
            indent = "|   " * self.depth
            arg_list = [repr(a) for a in args] + [f"{k}={v!r}" for k, v in kwargs.items()]
            all_args = ", ".join(arg_list)

            input_str = ""
            if self.show_input:
                input_str = f"({all_args})"

            # Log CALL
            self._log(f"{indent}|--> CALL {func.__name__}{input_str}")
            
            self.depth += 1
            start_time = time.perf_counter()
            
            try:
                # 3. EXECUTE
                result = func(*args, **kwargs)
                
                # 4. TEARDOWN
                time_str = ""
                if self.show_timing:
                    elapsed = (time.perf_counter() - start_time) * 1000
                    time_str = f" [Time: {elapsed:.2f}ms]"

                output_str = ""
                if self.show_output:
                    output_str = f": {repr(result)}"

                self.depth -= 1
                self._log(f"{indent}|<-- RETURN {func.__name__}{output_str}{time_str}")
                return result

            except Exception as e:
                self.depth -= 1
                self._log(f"{indent}|<-- ERROR {func.__name__}: {type(e).__name__}: {e}")
                raise e
                
            finally:
                # 5. RESTORE STDOUT
                # If we are back to depth 0, put the original stdout back
                if self.depth == 0:
                    sys.stdout = self.original_stdout
                    if self._file_handle:
                        self._file_handle.close()
                        self._file_handle = None

        return wrapper

# # How to Use
# trace = StackTracer(show_timing=True)